#pragma once
// Visit blob: what the device publishes so a visit can be replayed
// off-device exactly as the state machine saw it.
//
// Two messages per visit, both JSON:
//
//   visit/chunk  (QoS 1, not retained) — a slice of the WeightBuffer, sent
//                every CHUNK_SAMPLES during the visit and once more for the
//                tail at the end:
//                {"id","seq","first","n","s":[int16...]}
//
//   visit/last   (QoS 1, retained) — the end record: identity, timing, the
//                zone table that decodes the chunks, the device verdict and
//                the configuration it ran under. Published for short events
//                too (visit null), so the hub sees what the device skipped.
//
// Replay: rebuild the buffer from the raw samples and zones, then feed
// sample_to_grams(i) to process_sample(i) in order. The zone for sample i
// is opened by process_sample(i-1), same on device and replay. Drops list
// (index, gap_ms) for every accepted sample that arrived more than
// DROP_GAP_MS after the previous one; the analyzer is index-based, so that
// is all replay needs to know about time.
//
// Pure string building: no ESPHome or MQTT symbols, so the replay harness
// can share the format.
#include "state_analyzer.h"

#include <cstdint>
#include <cstdio>
#include <ctime>
#include <string>

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
  static const int CHUNK_SAMPLES = 2000;
  static const int MAX_DROPS = 256;
  static const uint32_t DROP_GAP_MS = 150;

  void begin(time_t id) {
    id_ = id;
    sent_ = 0;
    seq_ = 0;
    failed_ = 0;
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

  bool chunk_due(const WeightBuffer &buf) const { return buf.count() - sent_ >= CHUNK_SAMPLES; }

  /** Build the next chunk into `out`; false when nothing is pending. */
  bool next_chunk(const WeightBuffer &buf, std::string &out) {
    int n = buf.count() - sent_;
    if (n <= 0) return false;
    if (n > CHUNK_SAMPLES) n = CHUNK_SAMPLES;
    out.clear();
    out.reserve(64 + n * 7);
    char tmp[64];
    snprintf(tmp, sizeof(tmp), "{\"id\":%lld,\"seq\":%d,\"first\":%d,\"n\":%d,\"s\":[",
             static_cast<long long>(id_), seq_, sent_, n);
    out += tmp;
    for (int i = 0; i < n; i++) {
      snprintf(tmp, sizeof(tmp), i ? ",%d" : "%d", static_cast<int>(buf.raw_sample(sent_ + i)));
      out += tmp;
    }
    out += "]}";
    sent_ += n;
    seq_++;
    return true;
  }

  /** A chunk publish that the client refused; counted into the end record. */
  void chunk_failed() { failed_++; }
  int chunks() const { return seq_; }

  void end_record(const WeightBuffer &buf, const BlobEnd &e, const BlobConfig &c, std::string &out) const {
    out.clear();
    out.reserve(2048 + buf.zone_count() * 40 + drop_count_ * 16 +
                (e.visit ? e.visit->period_count * 40 : 0));
    char tmp[512];

    snprintf(tmp, sizeof(tmp),
             "{\"id\":%lld,\"ended\":%lld,\"clock_valid\":%s,\"duration\":%d,"
             "\"samples\":%d,\"stored\":%d,\"chunks\":%d,\"chunks_failed\":%d,"
             "\"long_enough\":%s,\"continued\":%s,",
             static_cast<long long>(e.id), static_cast<long long>(e.ended), b(e.clock_valid),
             e.duration_s, e.samples, buf.count(), seq_, failed_, b(e.long_enough), b(e.continued));
    out += tmp;

    out += "\"drops\":[";
    for (int i = 0; i < drop_count_; i++) {
      snprintf(tmp, sizeof(tmp), i ? ",[%d,%u]" : "[%d,%u]", drops_[i].index,
               static_cast<unsigned>(drops_[i].gap_ms));
      out += tmp;
    }
    snprintf(tmp, sizeof(tmp), "],\"drops_overflow\":%s,", b(drops_overflow_));
    out += tmp;

    out += "\"zones\":[";
    for (int i = 0; i < buf.zone_count(); i++) {
      const ZoneEntry &z = buf.zone(i);
      snprintf(tmp, sizeof(tmp), i ? ",[%d,%.9g,%d]" : "[%d,%.9g,%d]", z.start, z.baseline_g,
               static_cast<int>(z.scale));
      out += tmp;
    }
    out += "],";

    if (e.visit) {
      const StateResult &v = *e.visit;
      snprintf(tmp, sizeof(tmp),
               "\"visit\":{\"cat_weight\":%.9g,\"waste_weight\":%.9g,\"type\":\"%s\",\"cat\":%d,"
               "\"periods\":[",
               v.cat_weight, v.waste_weight, elimination_type_str(v.elimination_type), v.detected_cat);
      out += tmp;
      for (int i = 0; i < v.period_count; i++) {
        const StatePeriod &p = v.periods[i];
        snprintf(tmp, sizeof(tmp), i ? ",[\"%s\",%d,%d,%.9g]" : "[\"%s\",%d,%d,%.9g]",
                 analyzer_state_str(p.state), p.start, p.end, p.std_dev);
        out += tmp;
      }
      out += "]},";
    } else {
      out += "\"visit\":null,";
    }

    const BoxEvent &bx = *e.box;
    snprintf(tmp, sizeof(tmp),
             "\"box\":{\"kind\":\"%s\",\"level\":%.9g,\"added\":%.9g,\"box\":%.9g,"
             "\"zero_valid\":%s,\"zero\":%.9g,\"absent\":%s,\"scooped\":%s},",
             box_event_str(bx.kind), bx.level_g, bx.litter_added_g, bx.box_measured_g,
             b(bx.zero_valid), bx.zero_error_g, b(bx.absent), b(bx.scooped));
    out += tmp;

    out += "\"config\":{\"cat_weights\":[";
    for (int i = 0; i < SA_MAX_CATS; i++) {
      snprintf(tmp, sizeof(tmp), i ? ",%.9g" : "%.9g", c.cat_weights_kg[i]);
      out += tmp;
    }
    snprintf(tmp, sizeof(tmp),
             "],\"sd_threshold\":%.9g,\"tare\":%.9g,\"auto_tare\":%.9g,\"spike\":%.9g,"
             "\"vibration\":%.9g,\"activity_off\":%d,\"timeout\":%d,",
             c.sd_threshold_g, c.tare_kg, c.auto_tare_kg, c.spike_threshold_kg,
             c.vibration_threshold_kg, c.activity_off_s, c.event_timeout_s);
    out += tmp;
    snprintf(tmp, sizeof(tmp),
             "\"box\":{\"box_g\":%.9g,\"off_tol\":%.9g,\"empty_tol\":%.9g,\"lift\":%.9g,"
             "\"return_tol\":%.9g,\"top_up_min\":%.9g,\"scoop_min\":%.9g,\"scoop_min_s\":%d,"
             "\"settle_s\":%d}},",
             c.box.box_g, c.box.off_tol_g, c.box.empty_tol_g, c.box.lift_g, c.box.return_tol_g,
             c.box.top_up_min_g, c.box.scoop_min_g, c.box.scoop_min_s, c.box.settle_s);
    out += tmp;

    snprintf(tmp, sizeof(tmp), "\"fw\":{\"project\":\"%s\",\"version\":\"%s\"}}", e.project, e.version);
    out += tmp;
  }

 private:
  static const char *b(bool v) { return v ? "true" : "false"; }

  time_t id_ = 0;
  int sent_ = 0;
  int seq_ = 0;
  int failed_ = 0;
  SampleDrop drops_[MAX_DROPS];
  int drop_count_ = 0;
  bool drops_overflow_ = false;
  uint32_t last_ms_ = 0;
};

inline VisitRecorder &get_visit_recorder() {
  static VisitRecorder instance;
  return instance;
}
