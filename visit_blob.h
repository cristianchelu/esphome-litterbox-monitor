#pragma once
// Visit blob: what the device publishes so a visit can be replayed
// off-device exactly as the state machine saw it.
//
// One message per visit on visit/last (QoS 0, retained), binary:
//
//   "LBV1"  u32 n  int16 x n (little-endian)  JSON trailer
//
// The samples are the WeightBuffer's codes verbatim. On the device they go
// to the journal as the visit runs and the trailer is streamed in after
// them at the end, so the frame only ever exists whole on flash. The
// trailer follows the last sample: identity, timing, the zone table that
// decodes the codes, the device verdict and the configuration it ran
// under. Published for short events too (visit null), so the hub sees what
// the device skipped.
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
#include <functional>

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

/** Takes the next `n` bytes of the frame; false stops the writer. */
using BlobSink = std::function<bool(const char *data, size_t n)>;

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

  /** The frame's first 8 bytes: "LBV1" and the sample count, little-endian. */
  static void header(uint8_t out[8], int count) {
    memcpy(out, "LBV1", 4);
    uint32_t n = static_cast<uint32_t>(count);
    for (int i = 0; i < 4; i++) out[4 + i] = static_cast<uint8_t>(n >> (8 * i));
  }

  /**
   * The trailer, streamed to `out` in pieces. On the device the header and
   * samples are already in the journal and this is all that is left.
   * Returns the trailer length, or 0 if `out` refused a piece.
   */
  size_t write_trailer(const WeightBuffer &buf, const BlobEnd &e, const BlobConfig &c, const BlobSink &out) {
    Cursor w{this, &out};
    trailer_(w, buf, e, c);
    w.flush();
    return w.failed ? 0 : w.total;
  }

  /** The whole frame, header to trailer, for tools that hold it in memory. */
  size_t write_frame(const WeightBuffer &buf, const BlobEnd &e, const BlobConfig &c, const BlobSink &out) {
    uint8_t h[8];
    header(h, buf.count());
    if (!out(reinterpret_cast<const char *>(h), 8)) return 0;
    for (int i = 0; i < buf.count(); i++) {
      int16_t v = buf.raw_sample(i);
      uint8_t le[2] = {static_cast<uint8_t>(v & 0xFF), static_cast<uint8_t>((v >> 8) & 0xFF)};
      if (!out(reinterpret_cast<const char *>(le), 2)) return 0;
    }
    size_t t = write_trailer(buf, e, c, out);
    return t ? 8 + 2 * static_cast<size_t>(buf.count()) + t : 0;
  }

 private:
  static const size_t STAGE = 1024;

  /**
   * Formats into the staging buffer and hands it to the sink whenever the
   * next piece would not fit. Every printf below is well under STAGE, so a
   * piece that does not fit an empty buffer is a bug, reported as failure.
   */
  struct Cursor {
    VisitRecorder *r;
    const BlobSink *out;
    size_t used = 0;
    size_t total = 0;
    bool failed = false;
    void flush() {
      if (failed || used == 0) return;
      if (!(*out)(r->stage_, used)) failed = true;
      total += used;
      used = 0;
    }
    void printf(const char *fmt, ...) __attribute__((format(printf, 2, 3))) {
      for (int attempt = 0; attempt < 2 && !failed; attempt++) {
        va_list ap;
        va_start(ap, fmt);
        int n = vsnprintf(r->stage_ + used, STAGE - used, fmt, ap);
        va_end(ap);
        if (n >= 0 && static_cast<size_t>(n) < STAGE - used) {
          used += n;
          return;
        }
        if (n < 0 || used == 0) break;
        flush();
      }
      failed = true;
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
  char stage_[STAGE];
  SampleDrop drops_[MAX_DROPS];
  int drop_count_ = 0;
  bool drops_overflow_ = false;
  uint32_t last_ms_ = 0;
};

inline VisitRecorder &get_visit_recorder() {
  static VisitRecorder instance;
  return instance;
}
