#pragma once
// Visit blob: what the device publishes so a visit can be replayed
// off-device exactly as the state machine saw it.
//
// One message per visit on visit/last (QoS 0, retained), binary:
//
//   "LBV1"  u32 n  int16 x n (little-endian)  JSON trailer
//
// The samples are the WeightBuffer's storage verbatim — the buffer is the
// frame, so nothing is copied to ship it. The trailer follows the last
// sample: identity, timing, the zone table that decodes the codes, the
// device verdict and the configuration it ran under. Published for short
// events too (visit null), so the hub sees what the device skipped.
//
// Replay: rebuild the buffer from the raw codes and zones, then feed
// sample_to_grams(i) to process_sample(i) in order. The zone for sample i
// is opened by process_sample(i-1), same on device and replay. Drops list
// (index, gap_ms) for every accepted sample that arrived more than
// DROP_GAP_MS after the previous one; the analyzer is index-based, so that
// is all replay needs to know about time.
//
// Hub side: n = readUInt32LE(4); samples = Int16Array at byte 8;
// meta = JSON.parse(bytes from 8 + 2n).
//
// Pure string building: no ESPHome or MQTT symbols, so the replay harness
// can share the format.
#include "state_analyzer.h"

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

struct SampleDrop {
  int index;        // the sample that arrived late
  uint16_t gap_ms;  // since the previous accepted sample
};

/** Everything finalize() ran under that is not in StateResult or BoxEvent. */
struct BlobConfig {
  float cat_weights_kg[SA_MAX_CATS];
  float sd_threshold_g;
  float tare_kg;
  float auto_tare_kg;
  float spike_threshold_kg;
  float vibration_threshold_kg;
  int activity_off_s;
  int event_timeout_s;
  BoxConfig box;
};

struct BlobEnd {
  time_t id;      // event_start epoch — the correlation key
  time_t ended;
  bool clock_valid;
  int duration_s;
  int samples;    // accepted samples (sample index at the end)
  bool long_enough;
  bool continued;
  const StateResult *visit;  // null when not long enough
  const BoxEvent *box;
  const char *project;
  const char *version;
};

class VisitRecorder {
 public:
  static const int MAX_DROPS = 256;
  static const uint32_t DROP_GAP_MS = 150;

  void begin(time_t id) {
    id_ = id;
    drop_count_ = 0;
    drops_overflow_ = false;
    last_ms_ = 0;
  }

  /** Call once per accepted sample, before the buffer push. */
  void sample(int index, uint32_t now_ms) {
    if (last_ms_ != 0) {
      uint32_t gap = now_ms - last_ms_;
      if (gap > DROP_GAP_MS) {
        if (drop_count_ < MAX_DROPS) {
          drops_[drop_count_++] = {index, static_cast<uint16_t>(gap > 65535 ? 65535 : gap)};
        } else {
          drops_overflow_ = true;
        }
      }
    }
    last_ms_ = now_ms;
  }

  /**
   * Write the header and trailer around the samples already in the buffer.
   * Returns the frame length in bytes; the frame starts at &buf.frame().
   */
  size_t finish(WeightBuffer &buf, const BlobEnd &e, const BlobConfig &c) const {
    VisitFrame &f = buf.frame();
    memcpy(f.magic, "LBV1", 4);
    f.count = static_cast<uint32_t>(buf.count());
    char *base = reinterpret_cast<char *>(&f);
    Cursor w{base + 8 + 2 * buf.count(), base + sizeof(VisitFrame)};
    trailer_(w, buf, e, c);
    if (w.overflow) {
      // Cannot happen with SA_FRAME_TAIL sized for full tables; keep the
      // frame parseable rather than ship a torn trailer.
      w = Cursor{base + 8 + 2 * buf.count(), base + sizeof(VisitFrame)};
      w.printf("{\"id\":%lld,\"stored\":%d,\"truncated\":true}", static_cast<long long>(e.id), buf.count());
    }
    return static_cast<size_t>(w.p - base);
  }

 private:
  /** Bounded writer over the tail of the frame. */
  struct Cursor {
    char *p;
    const char *end;
    bool overflow = false;
    void printf(const char *fmt, ...) __attribute__((format(printf, 2, 3))) {
      if (overflow) return;
      va_list ap;
      va_start(ap, fmt);
      int n = vsnprintf(p, end - p, fmt, ap);
      va_end(ap);
      if (n < 0 || n >= end - p) {
        overflow = true;
        return;
      }
      p += n;
    }
  };

  static const char *b(bool v) { return v ? "true" : "false"; }

  void trailer_(Cursor &w, const WeightBuffer &buf, const BlobEnd &e, const BlobConfig &c) const {
    w.printf("{\"id\":%lld,\"ended\":%lld,\"clock_valid\":%s,\"duration\":%d,"
             "\"samples\":%d,\"stored\":%d,\"long_enough\":%s,\"continued\":%s,",
             static_cast<long long>(e.id), static_cast<long long>(e.ended), b(e.clock_valid),
             e.duration_s, e.samples, buf.count(), b(e.long_enough), b(e.continued));

    w.printf("\"drops\":[");
    for (int i = 0; i < drop_count_; i++)
      w.printf(i ? ",[%d,%u]" : "[%d,%u]", drops_[i].index, static_cast<unsigned>(drops_[i].gap_ms));
    w.printf("],\"drops_overflow\":%s,", b(drops_overflow_));

    w.printf("\"zones\":[");
    for (int i = 0; i < buf.zone_count(); i++) {
      const ZoneEntry &z = buf.zone(i);
      w.printf(i ? ",[%d,%.9g,%d]" : "[%d,%.9g,%d]", z.start, z.baseline_g, static_cast<int>(z.scale));
    }
    w.printf("],");

    if (e.visit) {
      const StateResult &v = *e.visit;
      w.printf("\"visit\":{\"cat_weight\":%.9g,\"waste_weight\":%.9g,\"type\":\"%s\",\"cat\":%d,"
               "\"periods\":[",
               v.cat_weight, v.waste_weight, elimination_type_str(v.elimination_type), v.detected_cat);
      for (int i = 0; i < v.period_count; i++) {
        const StatePeriod &p = v.periods[i];
        w.printf(i ? ",[\"%s\",%d,%d,%.9g]" : "[\"%s\",%d,%d,%.9g]", analyzer_state_str(p.state), p.start,
                 p.end, p.std_dev);
      }
      w.printf("]},");
    } else {
      w.printf("\"visit\":null,");
    }

    const BoxEvent &bx = *e.box;
    w.printf("\"box\":{\"kind\":\"%s\",\"level\":%.9g,\"added\":%.9g,\"box\":%.9g,"
             "\"zero_valid\":%s,\"zero\":%.9g,\"absent\":%s,\"scooped\":%s},",
             box_event_str(bx.kind), bx.level_g, bx.litter_added_g, bx.box_measured_g, b(bx.zero_valid),
             bx.zero_error_g, b(bx.absent), b(bx.scooped));

    w.printf("\"config\":{\"cat_weights\":[");
    for (int i = 0; i < SA_MAX_CATS; i++) w.printf(i ? ",%.9g" : "%.9g", c.cat_weights_kg[i]);
    w.printf("],\"sd_threshold\":%.9g,\"tare\":%.9g,\"auto_tare\":%.9g,\"spike\":%.9g,"
             "\"vibration\":%.9g,\"activity_off\":%d,\"timeout\":%d,",
             c.sd_threshold_g, c.tare_kg, c.auto_tare_kg, c.spike_threshold_kg, c.vibration_threshold_kg,
             c.activity_off_s, c.event_timeout_s);
    w.printf("\"box\":{\"box_g\":%.9g,\"off_tol\":%.9g,\"empty_tol\":%.9g,\"lift\":%.9g,"
             "\"return_tol\":%.9g,\"top_up_min\":%.9g,\"scoop_min\":%.9g,\"scoop_min_s\":%d,"
             "\"settle_s\":%d}},",
             c.box.box_g, c.box.off_tol_g, c.box.empty_tol_g, c.box.lift_g, c.box.return_tol_g,
             c.box.top_up_min_g, c.box.scoop_min_g, c.box.scoop_min_s, c.box.settle_s);

    w.printf("\"fw\":{\"project\":\"%s\",\"version\":\"%s\"}}", e.project, e.version);
  }

  time_t id_ = 0;
  SampleDrop drops_[MAX_DROPS];
  int drop_count_ = 0;
  bool drops_overflow_ = false;
  uint32_t last_ms_ = 0;
};

inline VisitRecorder &get_visit_recorder() {
  static VisitRecorder instance;
  return instance;
}
