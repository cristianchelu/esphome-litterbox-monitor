#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

static const int SA_MAX_SAMPLES = 36000;
/** Long visits can oscillate often; dropping txs breaks post_process vs TS (was 128). */
static const int SA_MAX_TRANSITIONS = 2048;
/** Must cover all tx segments before merge (short visits can exceed 64 transitions). */
static const int SA_MAX_PERIODS = 256;
/** Max RMS windows for median-RMS metric at 10 Hz over SA_MAX_SAMPLES. */
static const int SA_MOTION_HZ = 10;
static const int SA_MAX_MOTION_WINDOWS = SA_MAX_SAMPLES / SA_MOTION_HZ;
static const int SA_MAX_CATS = 5;
/** Zones open on OCCUPIED entry/exit and on delta overflow; a fidgety visit needs room. */
static const int SA_MAX_ZONES = 256;
static const float SA_URINATION_STD_DEV_THRESHOLD_G = 4.0f;
static const int16_t SA_SCALE_ABS = 1;    // 1g, identical to previous behavior
static const int16_t SA_SCALE_DELTA = 10; // 0.1g, used during OCCUPIED/ELIMINATING
/**
 * Samples the buffer keeps in RAM. On the device the rest of a long visit
 * is read back from its journal entry on flash (see WeightBuffer), so this
 * only has to cover what the journal has not written yet: 4096 samples is
 * almost 7 minutes against a 2 KB chunk every ~100 s. Off the device
 * (replay, tests) the whole visit stays in RAM.
 */
#ifndef SA_RING_SAMPLES
#ifdef ESP_PLATFORM
#define SA_RING_SAMPLES 4096
#else
#define SA_RING_SAMPLES SA_MAX_SAMPLES
#endif
#endif
static const int SA_RING = SA_RING_SAMPLES;
static_assert(SA_RING > 0 && SA_RING <= SA_MAX_SAMPLES, "ring size");

/**
 * Scratch for median-RMS over eliminating windows.
 * Function-static so it lives in BSS (not the ESPHome 8 KiB loop stack / heap).
 * Single-threaded: only one finalize/replay at a time.
 */
inline float *sa_motion_rms_scratch() {
  static float buf[SA_MAX_MOTION_WINDOWS];
  return buf;
}

enum class AnalyzerState : uint8_t {
  EMPTY,
  ENTERING,
  OCCUPIED,
  ELIMINATING,
  GAP
};

enum class EliminationType : uint8_t {
  NO_ELIMINATION,
  URINATION,
  DEFECATION,
  BOTH,
  UNKNOWN
};

struct StatePeriod {
  AnalyzerState state;
  int start;
  int end;
  float std_dev;  // negative means undefined
};

struct StateTransition {
  AnalyzerState from;
  AnalyzerState to;
  int index;
};

struct StateResult {
  float cat_weight;
  float waste_weight;
  StatePeriod periods[SA_MAX_PERIODS];
  int period_count;
  EliminationType elimination_type;
  int detected_cat;  // 0-based index, -1 = unknown
};

struct ZoneEntry {
  int start;         // first sample index in this zone
  float baseline_g;  // 0.0 for absolute zones
  int16_t scale;     // SA_SCALE_ABS or SA_SCALE_DELTA
};

// Ring buffer for rolling statistics over a fixed window.
class Ring {
 public:
  Ring() : n_(0), i_(0), filled_(0) { memset(buf_, 0, sizeof(buf_)); }

  explicit Ring(int n) : n_(n), i_(0), filled_(0) {
    memset(buf_, 0, sizeof(buf_));
  }

  void push(float x) {
    buf_[i_] = x;
    i_ = (i_ + 1) % n_;
    if (filled_ < n_) filled_++;
  }

  float mean() const {
    if (!filled_) return 0.0f;
    float s = 0.0f;
    for (int k = 0; k < filled_; k++) s += buf_[k];
    return s / static_cast<float>(filled_);
  }

  // Sample variance (divides by n-1)
  float variance() const {
    if (filled_ < 2) return 0.0f;
    float m = mean();
    float s = 0.0f;
    for (int k = 0; k < filled_; k++) {
      float d = buf_[k] - m;
      s += d * d;
    }
    return s / static_cast<float>(filled_ - 1);
  }

  // Checks ALL n slots including unfilled zeros, matching the TS Array.every()
  // behavior where the buffer is pre-filled with zeros.
  template <typename Func>
  bool every(Func fn) const {
    for (int k = 0; k < n_; k++) {
      if (!fn(buf_[k])) return false;
    }
    return true;
  }

  int size() const { return filled_; }

  void reset(int n) {
    n_ = n;
    i_ = 0;
    filled_ = 0;
    memset(buf_, 0, sizeof(buf_));
  }

 private:
  static const int MAX_RING = 16;
  float buf_[MAX_RING];
  int n_;
  int i_;
  int filled_;
};

// Stores raw weight samples for post-hoc per-period variance calculation.
//
// Samples are stored in one of two encodings, tracked via a zone table:
//   Absolute zones (SA_SCALE_ABS=1):  int16_t(weight_g)          -- 1g precision
//   Delta zones (SA_SCALE_DELTA=10):  int16_t((weight_g-base)*10) -- 0.1g precision
//
// Delta zones are opened at each OCCUPIED entry; absolute zones at GAP/ENTERING,
// and whenever a delta zone would overflow (a cat heavier than 3.2 kg leaving
// mid-zone), so no stored sample is ever more than 0.5 g from what was read.
// elimination_motion_metric() decodes per zone and applies TS median-RMS metric.
//
// The buffer is the record of the visit: the analyzer consumes what push()
// returns, so the raw samples plus the zone table replay it exactly.
//
// Storage is a ring of the last SA_RING samples. Older ones are read from
// `backing`, the visit's samples as the journal wrote them (memory-mapped
// flash on the device), which covers the first `durable` samples. A sample
// that leaves the ring before it is durable is lost, and the visit with it:
// complete() goes false and the caller must not analyse or ship it.
class WeightBuffer {
 public:
  void reset() {
    count_ = 0;
    lost_ = false;
    backing_ = nullptr;
    durable_ = 0;
    zone_count_ = 0;
    current_zone_ = -1;
    begin_absolute_zone();
  }

  // Open an absolute (1g) zone starting at the current sample position.
  void begin_absolute_zone() {
    if (zone_count_ < SA_MAX_ZONES)
      zones_[current_zone_ = zone_count_++] = {count_, 0.0f, SA_SCALE_ABS};
  }

  // Open a delta (0.1g) zone with the given baseline starting at current position.
  void begin_delta_zone(float baseline_g) {
    if (zone_count_ < SA_MAX_ZONES)
      zones_[current_zone_ = zone_count_++] = {count_, baseline_g, SA_SCALE_DELTA};
  }

  /**
   * Store a sample and return what it decodes back to — the value the state
   * machine must consume so the buffer is an exact record of the visit.
   * Once the buffer is full nothing is stored and the input passes through;
   * the analyzer stops at MAX_SESSION samples anyway.
   */
  float push(float weight_g) {
    if (count_ >= SA_MAX_SAMPLES || current_zone_ < 0) return weight_g;
    const ZoneEntry *z = &zones_[current_zone_];
    float val = encode_(weight_g, *z);
    if (z->scale != SA_SCALE_ABS && (val > 32767.0f || val < -32768.0f)) {
      // The zone table can be full, in which case the sample clamps below.
      begin_absolute_zone();
      z = &zones_[current_zone_];
      val = encode_(weight_g, *z);
    }
    // Round, don't truncate: a decoded value re-encodes to the same code,
    // so a replay that pushes decoded grams rebuilds this buffer exactly.
    int16_t enc = static_cast<int16_t>(lroundf(std::max(-32768.0f, std::min(32767.0f, val))));
    // The slot about to be reused holds sample count_ - SA_RING.
    if (count_ >= SA_RING && (backing_ == nullptr || count_ - SA_RING >= durable_)) lost_ = true;
    ring_[count_ % SA_RING] = enc;
    count_++;
    return decode_(enc, *z);
  }

  /**
   * Rebuild verbatim from a published record (raw codes plus zone table).
   * `samples` must outlive the buffer when the record is longer than the ring.
   */
  void restore(const int16_t *samples, int n, const ZoneEntry *zones, int nz) {
    count_ = std::min(n, SA_MAX_SAMPLES);
    lost_ = false;
    backing_ = samples;
    durable_ = count_;
    int first = std::max(0, count_ - SA_RING);
    for (int i = first; i < count_; i++) ring_[i % SA_RING] = samples[i];
    zone_count_ = std::min(nz, SA_MAX_ZONES);
    memcpy(zones_, zones, zone_count_ * sizeof(ZoneEntry));
    current_zone_ = zone_count_ - 1;
  }

  /**
   * Where samples that have left the ring can be read, and how many of them
   * are there. Null when there is nowhere (no journal, or it gave up).
   */
  void set_backing(const int16_t *samples, int durable) {
    backing_ = samples;
    durable_ = samples ? durable : 0;
  }

  /** Every sample can still be read: the visit can be analysed and shipped. */
  bool complete() const { return !lost_ && (count_ <= SA_RING || backing_ != nullptr); }

  int count() const { return count_; }
  int zone_count() const { return zone_count_; }
  const ZoneEntry &zone(int i) const { return zones_[i]; }
  int16_t raw_sample(int idx) const {
    if (idx >= count_ - SA_RING) return ring_[idx % SA_RING];
    return backing_ ? backing_[idx] : 0;
  }

  /**
   * Frame bytes still held in RAM, for the journal to copy out: the samples
   * start at frame offset 8 (after "LBV1" and the count). Returns a pointer
   * to the byte at `off` and how many follow it contiguously, or null when
   * that sample has left the ring.
   */
  const uint8_t *frame_bytes(uint32_t off, uint32_t *avail) const {
    *avail = 0;
    if (off < 8 || (off & 1)) return nullptr;
    int s = static_cast<int>((off - 8) / 2);
    if (s >= count_ || s < count_ - SA_RING) return nullptr;
    int pos = s % SA_RING;
    *avail = 2 * static_cast<uint32_t>(std::min(SA_RING - pos, count_ - s));
    return reinterpret_cast<const uint8_t *>(&ring_[pos]);
  }

  /** Grams the analyzer saw for sample `idx`. */
  float sample_to_grams(int idx) const {
    const ZoneEntry *z = zone_for_index(idx);
    if (!z || idx < 0 || idx >= count_) return 0.0f;
    return decode_(raw_sample(idx), *z);
  }

  /**
   * Motion metric for an ELIMINATING period — matches TS processEvent:
   * slice [start+10, end+1-10), decode to grams, eliminatingPeriodMotionMetric(..., hz=10).
   *
   * No heap: decodes window-by-window; RMS list uses sa_motion_rms_scratch() BSS.
   */
  float elimination_motion_metric(int start, int end, int hz) const {
    const int trim = 10;
    int s = start + trim;
    int e = end + 1 - trim;
    if (s >= e || s < 0 || e > count_) return -1.0f;
    int n = e - s;
    if (n < 2) return -1.0f;

    const int ws = hz >= 1 ? hz : 1;
    if (n < ws) return rms_around_mean_range(s, n);

    const int window_count = n / ws;
    if (window_count > SA_MAX_MOTION_WINDOWS) return -1.0f;

    float *rms_values = sa_motion_rms_scratch();
    for (int w = 0; w < window_count; ++w)
      rms_values[w] = rms_around_mean_range(s + w * ws, ws);

    std::sort(rms_values, rms_values + window_count);
    const int mid = window_count / 2;
    if (window_count % 2)
      return rms_values[mid];
    return 0.5f * (rms_values[mid - 1] + rms_values[mid]);
  }

 private:
  const ZoneEntry *zone_for_index(int idx) const {
    for (int z = 0; z < zone_count_; ++z) {
      int next_start = (z + 1 < zone_count_) ? zones_[z + 1].start : count_;
      if (idx >= zones_[z].start && idx < next_start) return &zones_[z];
    }
    return nullptr;
  }

  static float encode_(float weight_g, const ZoneEntry &z) {
    float val = weight_g - z.baseline_g;
    if (z.scale != SA_SCALE_ABS) val *= z.scale;
    return val;
  }

  static float decode_(int16_t enc, const ZoneEntry &z) {
    float val = static_cast<float>(enc);
    if (z.scale == SA_SCALE_ABS) return val;
    return z.baseline_g + val / static_cast<float>(z.scale);
  }

  /** TS rmsAroundMean over decoded grams in [s, s+n) without a heap decode buffer. */
  float rms_around_mean_range(int s, int n) const {
    if (n < 2) return 0.0f;
    float sum = 0.0f;
    for (int i = 0; i < n; ++i) sum += sample_to_grams(s + i);
    float mean = sum / static_cast<float>(n);
    float sq = 0.0f;
    for (int i = 0; i < n; ++i) {
      float d = sample_to_grams(s + i) - mean;
      sq += d * d;
    }
    return sqrtf(sq / static_cast<float>(n));
  }

  int16_t ring_[SA_RING];
  int count_ = 0;
  bool lost_ = false;
  const int16_t *backing_ = nullptr;
  int durable_ = 0;
  ZoneEntry zones_[SA_MAX_ZONES];
  int zone_count_ = 0;
  int current_zone_ = -1;
};

class StateAnalyzer {
 public:
  void init(const float *known_weights_kg, int num_cats) {
    num_known_ = 0;
    for (int i = 0; i < SA_MAX_CATS; i++) {
      slot_g_[i] = 0.0f;
      cat_presence_[i] = 0;
    }
    for (int i = 0; i < num_cats && i < SA_MAX_CATS; i++) {
      if (known_weights_kg[i] > 0.0f) {
        slot_g_[i] = known_weights_kg[i] * 1000.0f;
        known_g_[num_known_++] = slot_g_[i];
      }
    }
    std::sort(known_g_, known_g_ + num_known_);
    reset();
  }

  void attach_buffer(WeightBuffer *buf) { wbuf_ = buf; }

  /** `weight` in grams (float — matches firmware HX711 path). */
  void process_sample(float weight, int index) {
    // Stop updating rings/state once the weight buffer is full (1 h at 10 Hz).
    if (session_active_ && index - session_start_ > MAX_SESSION) return;

    current_weight_g_ = weight;
    current_sample_ = index;
    window_.push(weight);
    weight_hist_.push(weight);
    float mean1s = window_.mean();
    mean_hist_.push(mean1s);
    float var10 = weight_hist_.variance();
    float var10sample = var10 > 0.0f ? sqrtf(var10) : 0.0f;
    bool stable_now = var10sample > 0.0f && var10sample < STABLE_VARIANCE_SQRT;

    float entry_delta = entry_threshold();
    float presence_th =
        cat_weight_ > 0.0f ? cat_weight_ * PRESENCE_FRAC : entry_delta;

    switch (state_) {
      case AnalyzerState::EMPTY:
        if (mean1s > entry_delta) {
          start_session();
          transition_to(AnalyzerState::ENTERING);
        }
        break;

      case AnalyzerState::ENTERING:
        if (!confirm_presence(mean1s)) {
          if (mean1s < 0.5 * entry_delta)
            transition_to(AnalyzerState::GAP, WINDOW / 2);
          break;
        }
        if (mean_hist_.variance() < 10.0f &&
            mean_hist_.every(
                [this](float m) { return near_known(m); })) {
          transition_to(AnalyzerState::OCCUPIED, WINDOW / 2);
        } else {
          stable_cnt_ = 0;
        }
        break;

      case AnalyzerState::OCCUPIED: {
        int ci = closest_known_cat(mean1s);
        if (ci >= 0) cat_presence_[ci]++;
        if (stable_now && near_known(mean1s))
          transition_to(AnalyzerState::ELIMINATING);
        if (weight < entry_delta) {
          transition_to(AnalyzerState::GAP, WINDOW);
          exit_below_ = 0;
          break;
        }
        if (cat_weight_ > 0.0f &&
            cat_weight_ - mean1s > presence_th) {
          if (++exit_below_ >= EXIT_HOLD) {
            exit_below_ = 0;
            gap_cnt_ = 0;
            transition_to(AnalyzerState::ENTERING, WINDOW);
          }
        } else {
          exit_below_ = 0;
        }
        break;
      }

      case AnalyzerState::ELIMINATING: {
        int ci_elim = closest_known_cat(mean1s);
        if (ci_elim >= 0) cat_presence_[ci_elim]++;
        if (stable_now) {
          stable_cnt_++;
          elim_sum_ += mean1s;
          elim_count_++;
          cat_weight_ = elim_sum_ / static_cast<float>(elim_count_);
        } else {
          if (elim_count_ > best_elim_dur_) {
            best_elim_dur_ = elim_count_;
            best_elim_weight_ = elim_sum_ / static_cast<float>(elim_count_);
          }
          elim_sum_ = 0.0f;
          elim_count_ = 0;
          stable_cnt_ = 0;
          transition_to(AnalyzerState::OCCUPIED);
        }
        if (cat_weight_ > 0.0f &&
            cat_weight_ - mean1s > presence_th) {
          if (++exit_below_ >= EXIT_HOLD) {
            exit_below_ = 0;
            gap_cnt_ = 0;
            transition_to(AnalyzerState::GAP);
          }
        } else {
          exit_below_ = 0;
        }
        break;
      }

      case AnalyzerState::GAP:
        gap_cnt_++;
        if (mean1s > entry_delta) {
          if (stable_now) {
            if (near_known(mean1s))
              transition_to(AnalyzerState::ELIMINATING);
          } else {
            transition_to(AnalyzerState::ENTERING);
          }
        } else if (gap_cnt_ > REENTRY_WIN) {
          waste_weight_ = static_cast<float>(weight);
          return;
        }
        break;
    }
  }

  // Call after the session ends to compute final results.
  // Requires the WeightBuffer that was filled alongside process_sample calls.
  //
  // Returns a reference to member storage — do NOT put StateResult on the
  // ESPHome loop stack (periods[SA_MAX_PERIODS] alone is ~4 KiB).
  const StateResult &finalize(const WeightBuffer &buf,
                              const float *known_weights_kg,
                              int num_cats,
                              float std_dev_threshold = SA_URINATION_STD_DEV_THRESHOLD_G) {
    float best_w = best_elim_weight_;
    if (elim_count_ > best_elim_dur_ && elim_count_ > 0)
      best_w = elim_sum_ / static_cast<float>(elim_count_);
    result_.cat_weight = (best_w > 0.0f) ? best_w : cat_weight_;
    // The event usually closes a few seconds after the cat leaves, well
    // before REENTRY_WIN, so the GAP branch never gets to set the waste.
    // What the scale settled on over the last second of that gap is the
    // same thing end_event tares away, so take it from there.
    if (state_ == AnalyzerState::GAP && current_sample_ - state_start_ >= WINDOW)
      waste_weight_ = window_.mean();
    result_.waste_weight = waste_weight_;
    result_.period_count = 0;
    result_.elimination_type = EliminationType::UNKNOWN;
    result_.detected_cat = -1;

    post_process(result_.periods, result_.period_count);

    for (int i = 0; i < result_.period_count; i++) {
      result_.periods[i].std_dev =
          buf.elimination_motion_metric(result_.periods[i].start, result_.periods[i].end, HZ);
    }

    result_.elimination_type =
        classify_elimination(result_.periods, result_.period_count, std_dev_threshold);

    result_.detected_cat = detected_cat_from_presence();

    return result_;
  }

  void reset() {
    state_ = AnalyzerState::EMPTY;
    state_start_ = 0;
    session_active_ = false;
    window_.reset(WINDOW);
    weight_hist_.reset(WINDOW);
    mean_hist_.reset(3);
    cat_weight_ = 0.0f;
    elim_sum_ = 0.0f;
    elim_count_ = 0;
    best_elim_weight_ = 0.0f;
    best_elim_dur_ = 0;
    exit_below_ = 0;
    gap_cnt_ = 0;
    stable_cnt_ = 0;
    tx_count_ = 0;
    waste_weight_ = 0.0f;
    for (int i = 0; i < SA_MAX_CATS; i++) cat_presence_[i] = 0;
  }

  AnalyzerState current_state() const { return state_; }

 private:
  static constexpr int HZ = 10;
  /** sqrt(250) — TS compares sqrt(sample var) to this (not variance to 250). */
  static constexpr float STABLE_VARIANCE_SQRT = 15.811388f;
  static constexpr float STABLE_MERGE_GAP = 1.5f * HZ;
  static constexpr float ENTRY_DELTA_MIN = 1200.0f;
  static constexpr float ENTRY_DELTA_FRAC = 0.22f;
  static constexpr float PRESENCE_FRAC = 0.28f;
  static constexpr int EXIT_HOLD = 6;
  static constexpr int REENTRY_WIN = 15 * HZ;
  /** At 10 Hz, 36000 samples = 1 h — matches SA_MAX_SAMPLES. */
  static constexpr int MAX_SESSION = 60 * 60 * HZ;
  static constexpr float KNOWN_TOL = 0.1f;
  static constexpr int WINDOW = 10;

  AnalyzerState state_ = AnalyzerState::EMPTY;
  float known_g_[SA_MAX_CATS] = {};
  /** Known cat weight per config slot (g); 0 = empty. Same indexing as init() input (sorted in replay). */
  float slot_g_[SA_MAX_CATS] = {};
  int cat_presence_[SA_MAX_CATS] = {};
  int num_known_ = 0;
  Ring window_{WINDOW};
  Ring weight_hist_{WINDOW};
  Ring mean_hist_{3};
  int exit_below_ = 0;
  int gap_cnt_ = 0;
  int stable_cnt_ = 0;
  bool session_active_ = false;
  int session_start_ = 0;
  int current_sample_ = 0;
  int state_start_ = 0;  // sample on which state_ was entered (not backdated)
  float waste_weight_ = 0.0f;
  float cat_weight_ = 0.0f;
  float elim_sum_ = 0.0f;
  int elim_count_ = 0;
  float best_elim_weight_ = 0.0f;
  int best_elim_dur_ = 0;
  float current_weight_g_ = 0.0f;
  WeightBuffer *wbuf_ = nullptr;
  StateTransition txs_[SA_MAX_TRANSITIONS];
  int tx_count_ = 0;
  /** Finalize output — BSS, not loop-stack. */
  StateResult result_{};
  /**
   * Shared period scratch for post_process then classify_elimination
   * (sequential; never live at the same time). Keeps ~4 KiB off the stack.
   */
  StatePeriod period_scratch_[SA_MAX_PERIODS] = {};

  float entry_threshold() const {
    float min_known = num_known_ > 0 ? known_g_[0] : 0.0f;
    return min_known > 0.0f
               ? std::max(ENTRY_DELTA_MIN, min_known * ENTRY_DELTA_FRAC)
               : ENTRY_DELTA_MIN;
  }

  void start_session() {
    session_active_ = true;
    session_start_ = current_sample_;
    cat_weight_ = 0.0f;
    elim_sum_ = 0.0f;
    elim_count_ = 0;
    best_elim_weight_ = 0.0f;
    best_elim_dur_ = 0;
    exit_below_ = 0;
    gap_cnt_ = 0;
    stable_cnt_ = 0;
    tx_count_ = 0;
    for (int i = 0; i < SA_MAX_CATS; i++) cat_presence_[i] = 0;
  }

  void transition_to(AnalyzerState ns, int offset = 0) {
    if (state_ == ns) return;
    if (session_active_ && ns == AnalyzerState::EMPTY) {
      state_ = ns;
      session_active_ = false;
      return;
    }
    if (tx_count_ < SA_MAX_TRANSITIONS)
      txs_[tx_count_++] = {state_, ns, current_sample_ - offset};
    if (wbuf_) {
      if (ns == AnalyzerState::OCCUPIED && state_ != AnalyzerState::ELIMINATING) {
        wbuf_->begin_delta_zone(current_weight_g_);
      } else if ((ns == AnalyzerState::GAP || ns == AnalyzerState::ENTERING) &&
                 (state_ == AnalyzerState::OCCUPIED ||
                  state_ == AnalyzerState::ELIMINATING)) {
        wbuf_->begin_absolute_zone();
      }
    }
    state_ = ns;
    state_start_ = current_sample_;
  }

  /** among cats within tolerance, smallest absolute diff wins. */
  int closest_known_cat(float val_g, float tol = KNOWN_TOL) const {
    int best = -1;
    float min_diff = 1e9f;
    for (int i = 0; i < SA_MAX_CATS; i++) {
      float w = slot_g_[i];
      if (w <= 0.0f) continue;
      float diff = std::abs(val_g - w);
      if (diff <= w * tol && diff < min_diff) {
        min_diff = diff;
        best = i;
      }
    }
    return best;
  }

  /** highest count wins; ties go to lower slot index. */
  int detected_cat_from_presence() const {
    int best = -1;
    int best_count = 0;
    for (int i = 0; i < SA_MAX_CATS; i++) {
      if (slot_g_[i] <= 0.0f) continue;
      if (cat_presence_[i] > best_count) {
        best_count = cat_presence_[i];
        best = i;
      }
    }
    return best_count > 0 ? best : -1;
  }

  bool near_known(float val, float tol = KNOWN_TOL) const {
    for (int i = 0; i < num_known_; i++) {
      float w = known_g_[i];
      if (w > 0.0f && std::abs(val - w) / w <= tol) return true;
    }
    return false;
  }

  bool confirm_presence(float rel) const {
    return near_known(rel) || rel > entry_threshold();
  }

  void post_process(StatePeriod *out, int &count) {
    count = 0;
    if (tx_count_ == 0) return;

    StatePeriod *tmp = period_scratch_;
    int n = 0;

    for (int i = 0; i < tx_count_ && n < SA_MAX_PERIODS; i++) {
      int s = (i == 0) ? session_start_ : txs_[i].index;
      int e = (i + 1 < tx_count_) ? txs_[i + 1].index : current_sample_;
      AnalyzerState st = txs_[i].to;
      if (st != AnalyzerState::EMPTY && e > s)
        tmp[n++] = {st, s, e, -1.0f};
    }

    // Merge short OCCUPIED gaps between ELIMINATING periods
    for (int i = 1; i < n - 1; i++) {
      if (tmp[i - 1].state == AnalyzerState::ELIMINATING &&
          tmp[i].state == AnalyzerState::OCCUPIED &&
          tmp[i + 1].state == AnalyzerState::ELIMINATING &&
          (tmp[i].end - tmp[i].start) < (int)STABLE_MERGE_GAP &&
          (tmp[i - 1].end - tmp[i - 1].start) > HZ &&
          (tmp[i + 1].end - tmp[i + 1].start) > HZ) {
        tmp[i - 1].end = tmp[i + 1].end;
        for (int j = i; j < n - 2; j++) tmp[j] = tmp[j + 2];
        n -= 2;
        i--;
      }
    }

    // Downgrade short ELIMINATING periods
    const int min_elim = 5 * HZ;
    for (int i = 0; i < n; i++) {
      if (tmp[i].state == AnalyzerState::ELIMINATING &&
          (tmp[i].end - tmp[i].start) < min_elim)
        tmp[i].state = AnalyzerState::OCCUPIED;
    }

    if (n == 0) return;

    // Merge consecutive same-state periods
    out[0] = tmp[0];
    count = 1;
    for (int i = 1; i < n; i++) {
      if (tmp[i].state == out[count - 1].state) {
        out[count - 1].end = tmp[i].end;
      } else if (count < SA_MAX_PERIODS) {
        out[count++] = tmp[i];
      }
    }
  }

  EliminationType classify_elimination(const StatePeriod *p,
                                       int count,
                                       float threshold) {
    StatePeriod *elim = period_scratch_;
    int ec = 0;
    for (int i = 0; i < count; i++) {
      if (p[i].state == AnalyzerState::ELIMINATING && p[i].std_dev >= 0.0f)
        elim[ec++] = p[i];
    }

    if (ec == 0) return EliminationType::NO_ELIMINATION;
    if (ec == 1)
      return elim[0].std_dev < threshold
                 ? EliminationType::URINATION
                 : EliminationType::DEFECATION;
    if (ec == 2) {
      bool a_uri = elim[0].std_dev < threshold;
      bool b_uri = elim[1].std_dev < threshold;
      if (a_uri != b_uri) return EliminationType::BOTH;
    }
    return EliminationType::UNKNOWN;
  }

};

// ---------------------------------------------------------------------------
// BoxMonitor — what is on the scale besides a cat.
//
// Runs on the absolute (calibrated, un-tared) weight at 10 Hz, always, not only
// during activity: the interesting moments straddle event boundaries (the box
// leaves in one event and comes back in the next). Absolute grams make the
// shapes unambiguous where event-relative deltas are not:
//   raw < -lift_g        the whole monitor is in the air, frame hanging
//   |raw| < off_tol      bare board — the box is off, and 0 g is a known weight
//   raw ≈ box_g          the box came back empty: a deep clean
//   then +N kg steps     bags of litter poured in, evened out, left alone
// Per event it also keeps the list of plateaus (stable ≥ 2 s) so the end-of-
// event classifier can ask "rose monotonically, then went inert?".
// ---------------------------------------------------------------------------

static const int BM_MAX_PLATEAUS = 32;

enum class BoxState : uint8_t { NORMAL, LIFTED, OFF, EMPTY };

enum class BoxEventKind : uint8_t { NONE, LIFTED, DEEP_CLEAN, TOP_UP, SCOOP };

struct Plateau {
  int start;
  int end;  // exclusive
  float mean_g;
  float sigma_g;
};

struct BoxConfig {
  float box_g;         // configured empty box weight; 0 = unknown (no deep-clean detection)
  float off_tol_g;     // |raw| below this, stable: box off (and zero check)
  float empty_tol_g;   // |raw - box_g| below this, stable, after absence: deep clean
  float lift_g;        // raw below -lift_g: monitor lifted
  float return_tol_g;  // put back within this of the pre-event level: nothing changed
  float top_up_min_g;  // smallest rise reported as a top-up
  float scoop_min_g;   // drop (positive number) that counts as a scoop
  int scoop_min_s;     // ...unless the event is at least this long
  int settle_s;        // inert seconds before a top-up ends the event
};

struct BoxEvent {
  BoxEventKind kind;
  float level_g;         // absolute level at the end (last plateau if there is one)
  float litter_added_g;  // deep clean / top-up: how much went in
  float box_measured_g;  // deep clean: what the empty box actually weighed
  float zero_error_g;    // bare-board reading, valid when zero_valid
  bool zero_valid;
  bool absent;           // box not on the board at the end — do not tare
  bool scooped;          // top-up: litter came out before the bag went in
};

class BoxMonitor {
 public:
  void configure(const BoxConfig &c) { cfg_ = c; }
  const BoxConfig &config() const { return cfg_; }

  /** `base_g`: absolute level the event is measured against (the last tare). */
  void begin_event(float base_g) {
    base_g_ = base_g;
    ev_start_ = n_;
    pl_count_ = 0;
    pl_overflow_ = false;
    saw_lifted_ = false;
    saw_off_ = false;
    began_absent_ = absent_;
    deep_clean_ = false;
    empty_pl_ = -1;
    zero_valid_ = false;
    zero_error_g_ = 0.0f;
    box_measured_g_ = 0.0f;
    inert_len_ = 0;
  }

  /** Every sample, in absolute grams, event or not. */
  void process(float g) {
    n_++;
    win_.push(g);
    if (win_.size() < WINDOW) return;
    float m = win_.mean();
    float sd = sqrtf(win_.variance());
    bool stable = sd < PLATEAU_SIGMA;

    if (stable) {
      if (pl_n_ == 0) pl_start_ = n_ - WINDOW;
      pl_n_++;
      double d = g - pl_mean_;
      pl_mean_ += d / pl_n_;
      pl_m2_ += d * (g - pl_mean_);
    } else if (pl_n_ > 0) {
      close_plateau();
    }
    inert_len_ = sd < INERT_SIGMA ? inert_len_ + 1 : 0;

    // Box state. Absence latches until a stable plateau with something in
    // the box shows up again, so "off in one event, back in the next" works.
    bool absent_now = below_box(m);
    if (m < -cfg_.lift_g) {
      state_ = BoxState::LIFTED;
      saw_lifted_ = true;
      absent_ = true;
      hold_ = 0;
    } else if (stable && std::abs(m) < cfg_.off_tol_g) {
      state_ = BoxState::OFF;
      saw_off_ = true;
      absent_ = true;
      if (++hold_ >= HOLD && pl_n_ >= HOLD) {
        zero_error_g_ = static_cast<float>(pl_mean_);
        zero_valid_ = true;
      }
    } else if (stable && cfg_.box_g > 0.0f && (absent_ || state_ == BoxState::EMPTY) &&
               std::abs(m - cfg_.box_g) < cfg_.empty_tol_g) {
      if (state_ != BoxState::EMPTY && ++hold_ >= HOLD) {
        state_ = BoxState::EMPTY;
        deep_clean_ = true;
        box_measured_g_ = static_cast<float>(pl_mean_);
        empty_pl_ = pl_count_;  // the open plateau closes into this slot
        absent_ = false;
      }
    } else {
      if (absent_now) absent_ = true;
      else if (stable) absent_ = false;
      if (state_ == BoxState::LIFTED || state_ == BoxState::OFF) {
        if (!absent_now) state_ = BoxState::NORMAL;
      } else if (state_ == BoxState::EMPTY && stable) {
        state_ = BoxState::NORMAL;
      }
      hold_ = 0;
    }
  }

  BoxState state() const { return state_; }
  bool absent() const { return absent_; }

  /**
   * True once the stability window is full and `state()` means something. Until
   * then it is only the NORMAL it was constructed with, which is a guess: a
   * board that boots with the box off reads normal for the first second.
   */
  bool ready() const { return win_.size() >= WINDOW; }

  /**
   * True once a top-up (or a deep clean plus refill) has gone inert for
   * settle_s: the box is settled and the event can end without waiting for the
   * inactivity timeout. Inertness alone is the proof there is no cat — a bag
   * can weigh exactly what a cat does, but no cat holds σ < 1 g for 30 s.
   */
  bool settled() const {
    if (inert_len_ < cfg_.settle_s * HZ || absent_) return false;
    return deep_clean_ || current_level() - base_g_ >= cfg_.top_up_min_g;
  }

  /**
   * Classify the event. Call once, at event end, before taring.
   * `cat_event`: the analyzer saw a known cat during this event. Only scoops
   * defer to it; a rise that went inert is litter whatever the analyzer
   * matched it to, and the caller drops the visit.
   */
  const BoxEvent &finalize(int duration_s, bool cat_event) {
    bool ended_stable = pl_n_ >= MIN_PLATEAU;
    bool ended_inert = inert_len_ >= cfg_.settle_s * HZ;
    if (ended_stable) close_plateau();
    BoxEvent &r = result_;
    r.kind = BoxEventKind::NONE;
    r.level_g = pl_count_ > 0 ? pl_[pl_count_ - 1].mean_g : win_.mean();
    r.litter_added_g = 0.0f;
    r.box_measured_g = box_measured_g_;
    r.zero_error_g = zero_error_g_;
    r.zero_valid = zero_valid_;
    r.absent = absent_;
    r.scooped = false;
    float delta = r.level_g - base_g_;

    if (absent_) {
      // Still off or in the air: nothing to conclude until it comes back.
      r.kind = state_ == BoxState::LIFTED ? BoxEventKind::LIFTED : BoxEventKind::NONE;
      return r;
    }
    if (deep_clean_) {
      r.kind = BoxEventKind::DEEP_CLEAN;
      // The box came back empty, so whatever is in it now went in since.
      if (r.level_g > box_measured_g_ + cfg_.top_up_min_g)
        r.litter_added_g = r.level_g - box_measured_g_;
      return r;
    }
    // The whole monitor went up and came back down: a few grams of settling
    // is not a scoop, the box was never opened.
    if (saw_lifted_ && std::abs(delta) < cfg_.return_tol_g) {
      r.kind = BoxEventKind::LIFTED;
      return r;
    }
    // The box went off and came back with nothing taken out or put in.
    if ((saw_off_ || began_absent_) && delta > -cfg_.scoop_min_g &&
        delta < cfg_.return_tol_g) {
      r.kind = BoxEventKind::LIFTED;
      return r;
    }
    // A rise that went inert is litter whatever it weighs: a bag can match a
    // cat to the gram, but no cat holds still this long. Measured from the
    // lowest point of the event rather than its start, so scooping before
    // the pour is not subtracted from the bag (it is reported alongside).
    int ls = ladder_start();
    float from = ls < pl_count_ ? std::min(base_g_, pl_[ls].mean_g) : base_g_;
    if (ended_inert && r.level_g - from >= cfg_.top_up_min_g && monotonic_from(ls)) {
      r.kind = BoxEventKind::TOP_UP;
      r.litter_added_g = r.level_g - from;
      r.scooped = base_g_ - from >= cfg_.scoop_min_g;
      return r;
    }
    // A lift-and-return needs no minimum duration: the absence already says
    // the box was opened, so a drop is a scoop however quick the hands were.
    if (!cat_event && delta <= -cfg_.scoop_min_g &&
        (duration_s >= cfg_.scoop_min_s || began_absent_ || saw_off_)) {
      r.kind = BoxEventKind::SCOOP;
      return r;
    }
    return r;
  }

  int plateau_count() const { return pl_count_; }
  const Plateau &plateau(int i) const { return pl_[i]; }

 private:
  static constexpr int HZ = 10;
  static constexpr int WINDOW = 10;
  /** Same bar as the analyzer's stability: sqrt(250). */
  static constexpr float PLATEAU_SIGMA = 15.811388f;
  /**
   * Inert: nothing alive on the box. Over 1552 verified visits the longest a
   * cat held a 1 s window under 1 g was 11 s; poured litter holds it forever.
   */
  static constexpr float INERT_SIGMA = 1.0f;
  static constexpr int MIN_PLATEAU = 2 * HZ;
  static constexpr int HOLD = 3 * HZ;
  /**
   * Successive plateau means jitter by a few grams (cell creep after a kilo
   * lands, a hand off the rim). A drop bigger than this is mass leaving.
   */
  static constexpr float LEVEL_TOL = 50.0f;

  BoxConfig cfg_{};
  Ring win_{WINDOW};
  int n_ = 0;
  BoxState state_ = BoxState::NORMAL;
  bool absent_ = false;
  int hold_ = 0;
  int inert_len_ = 0;
  // open plateau (Welford, double: sums of 1e4 g over 1e4 samples lose float bits)
  int pl_start_ = 0;
  int pl_n_ = 0;
  double pl_mean_ = 0.0;
  double pl_m2_ = 0.0;
  // per event
  float base_g_ = 0.0f;
  int ev_start_ = 0;
  Plateau pl_[BM_MAX_PLATEAUS];
  int pl_count_ = 0;
  bool pl_overflow_ = false;
  bool saw_lifted_ = false;
  bool saw_off_ = false;
  bool began_absent_ = false;
  bool deep_clean_ = false;
  int empty_pl_ = -1;
  float box_measured_g_ = 0.0f;
  float zero_error_g_ = 0.0f;
  bool zero_valid_ = false;
  BoxEvent result_{};

  /** Below anything the box can weigh: it is off the board (or the board is in the air). */
  bool below_box(float g) const {
    return cfg_.box_g > 0.0f ? g < 0.5f * cfg_.box_g : g < cfg_.off_tol_g;
  }

  /** Lowest plateau since the box was last away: where a pour starts from. */
  int ladder_start() const {
    int s = 0;
    for (int i = 0; i < pl_count_; i++)
      if (below_box(pl_[i].mean_g)) s = i + 1;
    int lo = s;
    for (int i = s + 1; i < pl_count_; i++)
      if (pl_[i].mean_g < pl_[lo].mean_g) lo = i;
    return lo;
  }

  void close_plateau() {
    if (pl_n_ >= MIN_PLATEAU && pl_start_ >= ev_start_) {
      float sigma = pl_n_ > 1 ? sqrtf(static_cast<float>(pl_m2_ / (pl_n_ - 1))) : 0.0f;
      if (pl_count_ < BM_MAX_PLATEAUS)
        pl_[pl_count_++] = {pl_start_, pl_start_ + pl_n_, static_cast<float>(pl_mean_), sigma};
      else
        pl_overflow_ = true;
    }
    pl_n_ = 0;
    pl_mean_ = 0.0;
    pl_m2_ = 0.0;
  }

  float current_level() const {
    return pl_n_ >= MIN_PLATEAU ? static_cast<float>(pl_mean_) : win_.mean();
  }

  /** Plateaus from `from` on never drop by more than the jitter tolerance. */
  bool monotonic_from(int from) const {
    if (pl_overflow_) return false;
    for (int i = from + 1; i < pl_count_; i++)
      if (pl_[i].mean_g < pl_[i - 1].mean_g - LEVEL_TOL) return false;
    return true;
  }
};

// Singleton accessors for use across ESPHome lambdas
inline StateAnalyzer &get_analyzer() {
  static StateAnalyzer instance;
  return instance;
}
inline WeightBuffer &get_weight_buf() {
  static WeightBuffer instance;
  return instance;
}
inline BoxMonitor &get_box_monitor() {
  static BoxMonitor instance;
  return instance;
}
inline int &get_sample_idx() {
  static int idx = 0;
  return idx;
}

inline const char *box_state_str(BoxState s) {
  switch (s) {
    case BoxState::NORMAL: return "normal";
    case BoxState::LIFTED: return "lifted";
    case BoxState::OFF:    return "off";
    case BoxState::EMPTY:  return "empty";
  }
  return "unknown";
}

inline const char *box_event_str(BoxEventKind k) {
  switch (k) {
    case BoxEventKind::NONE:       return "none";
    case BoxEventKind::LIFTED:     return "lifted";
    case BoxEventKind::DEEP_CLEAN: return "deep_clean";
    case BoxEventKind::TOP_UP:     return "top_up";
    case BoxEventKind::SCOOP:      return "scoop";
  }
  return "none";
}

inline const char *analyzer_state_str(AnalyzerState s) {
  switch (s) {
    case AnalyzerState::EMPTY:       return "empty";
    case AnalyzerState::ENTERING:    return "entering";
    case AnalyzerState::OCCUPIED:    return "occupied";
    case AnalyzerState::ELIMINATING: return "eliminating";
    case AnalyzerState::GAP:         return "gap";
  }
  return "unknown";
}

inline const char *elimination_type_str(EliminationType t) {
  switch (t) {
    case EliminationType::NO_ELIMINATION: return "no_elimination";
    case EliminationType::URINATION:      return "urination";
    case EliminationType::DEFECATION:     return "defecation";
    case EliminationType::BOTH:           return "both";
    case EliminationType::UNKNOWN:        return "unknown";
  }
  return "unknown";
}
