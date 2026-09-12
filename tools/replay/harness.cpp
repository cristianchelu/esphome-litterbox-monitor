// Native replay of BoxMonitor over recorded weight traces.
//
//   g++ -std=c++17 -O1 -Wall -o harness harness.cpp && ./harness < traces.txt
//
// Input: one absolute reading in grams per line, under a header line per
// recording:
//
//   # <id> <offset> <timestamp> n=<samples> dur=<seconds> <label> abs|chain
//
// The readings are already absolute (bare board = 0); `offset` is what was
// added to the event-relative trace to get there. `abs` recordings start
// from a fresh tracker with the tare at `offset`. `chain` recordings carry
// on from the previous one, tare and box state included, which is how a
// deep clean split over several recordings replays as one sequence.
// `dur` is the real length in seconds when the recording was not sampled
// at 10 Hz. An optional first argument overrides the empty box weight.
//
// Emulates the firmware's event handling: begin_event at the tare, early
// end on settled(), tare only when the box is present. Recordings that end
// with more than 0.9 kg above the tare are padded with their last seconds,
// because the old firmware cut events there while the new one keeps them
// open until the added mass settles.
#include "../../state_analyzer.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

static const char *kind(BoxEventKind k) { return box_event_str(k); }

int main(int argc, char **argv) {
  BoxConfig cfg{1320.0f, 300.0f, 150.0f, 1000.0f, 100.0f, 300.0f, 20.0f, 30, 30};
  if (argc > 1) cfg.box_g = atof(argv[1]);
  BoxMonitor bm;
  bm.configure(cfg);

  float tare = 0.0f;
  bool have_tare = false;
  std::string hdr;
  std::vector<float> w;
  float last = 0.0f;
  int real_dur = 0;  // seconds, from the recording's timestamps

  auto finish = [&](int n, bool early, int at) {
    // samples were recorded at ~6.5 Hz, not 10: scale the sub-event length
    int dur = real_dur > 0 ? (int) ((long) n * real_dur / std::max(1, (int) w.size())) : n / 10;
    const BoxEvent &r = bm.finalize(dur, false);
    printf("  @%4ds -> %-10s level=%6.0f delta=%6.0f added=%5.0f box=%5.0f zero=%s%.0f absent=%d%s  plateaus:",
           at / 10, kind(r.kind), r.level_g, r.level_g - tare, r.litter_added_g, r.box_measured_g,
           r.zero_valid ? "" : "?", r.zero_error_g, (int) r.absent, early ? " (settled early)" : "");
    if (r.scooped) printf(" +scoop");
    for (int i = 0; i < bm.plateau_count(); i++) {
      const Plateau &p = bm.plateau(i);
      printf(" %.0f(%ds,%.1f)", p.mean_g, (p.end - p.start) / 10, p.sigma_g);
    }
    printf("\n");
    if (!r.absent) tare = last;
  };

  auto run = [&]() {
    if (w.empty()) return;
    printf("%s\n", hdr.c_str());
    if (!have_tare) { tare = w[0]; have_tare = true; }
    bm.begin_event(tare);
    int start = 0;
    for (int i = 0; i < (int) w.size(); i++) {
      bm.process(w[i]);
      last = w[i];
      if (bm.settled()) {
        finish(i - start, true, i);
        start = i;
        bm.begin_event(tare);
      }
    }
    // The old firmware cut recordings where its own event ended; the new one
    // keeps the event open while the tared level latches occupancy (> 0.9 kg),
    // so pad such tails with 40 s of the recording's last 10 s, looped.
    int n = (int) w.size();
    if (last - tare > 900.0f) {
      int tail = std::min(100, (int) w.size());
      for (int i = 0; i < 400; i++) {
        bm.process(w[w.size() - tail + (i % tail)]);
        if (bm.settled()) { finish(n + i - start, true, n + i); start = n + i; bm.begin_event(tare); break; }
      }
      n += 400;
    }
    finish(n - start, false, n);
    // idle gap until the next event: hold the final level for 5 s
    for (int i = 0; i < 50; i++) bm.process(last);
    w.clear();
  };

  char line[256];
  while (fgets(line, sizeof line, stdin)) {
    if (line[0] == '#') {
      run();
      hdr = line;
      while (!hdr.empty() && (hdr.back() == '\n' || hdr.back() == '\r')) hdr.pop_back();
      real_dur = 0;
      const char *d = strstr(line, "dur=");
      if (d) real_dur = atoi(d + 4);
      int id; float off;
      if (sscanf(line, "# %d %f", &id, &off) == 2 && hdr.find(" abs") != std::string::npos) {
        tare = off;  // standalone event: its tare is the offset it was dumped with
        have_tare = true;
        bm = BoxMonitor();
        bm.configure(cfg);
      }
    } else {
      w.push_back(atof(line));
    }
  }
  run();
  return 0;
}
