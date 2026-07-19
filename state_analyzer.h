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
static const int SA_MAX_ZONES = 32;
static const float SA_URINATION_STD_DEV_THRESHOLD_G = 4.0f;
static const int16_t SA_SCALE_ABS = 1;    // 1g, identical to previous behavior
static const int16_t SA_SCALE_DELTA = 10; // 0.1g, used during OCCUPIED/ELIMINATING

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
// Delta zones are opened at each OCCUPIED entry; absolute zones at GAP/ENTERING.
// elimination_motion_metric() decodes per zone and applies TS median-RMS metric.
class WeightBuffer {
 public:
  void reset() {
    count_ = 0;
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

  void push(float weight_g) {
    if (count_ >= SA_MAX_SAMPLES || current_zone_ < 0) return;
    const ZoneEntry &z = zones_[current_zone_];
    float val = weight_g - z.baseline_g;
    if (z.scale != SA_SCALE_ABS) val *= z.scale;
    samples_[count_++] = static_cast<int16_t>(
        std::max(-32768.0f, std::min(32767.0f, val)));
  }

  int count() const { return count_; }

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

  float sample_to_grams(int idx) const {
    const ZoneEntry *z = zone_for_index(idx);
    if (!z || idx < 0 || idx >= count_) return 0.0f;
    float enc = static_cast<float>(samples_[idx]);
    if (z->scale == SA_SCALE_ABS) return enc;
    return z->baseline_g + enc / static_cast<float>(z->scale);
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

  int16_t samples_[SA_MAX_SAMPLES];
  int count_ = 0;
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

// Singleton accessors for use across ESPHome lambdas
inline StateAnalyzer &get_analyzer() {
  static StateAnalyzer instance;
  return instance;
}
inline WeightBuffer &get_weight_buf() {
  static WeightBuffer instance;
  return instance;
}
inline int &get_sample_idx() {
  static int idx = 0;
  return idx;
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
