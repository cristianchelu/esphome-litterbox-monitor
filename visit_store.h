#pragma once
// Visit store: a flash journal for visit frames and the task that ships them.
//
// The journal follows the visit instead of copying it out afterwards. At
// begin_event an entry is opened; every step() programs whatever whole
// chunk of the RAM frame has accumulated since (2 KB every ~100 s at
// 10 Hz, a few ms each); at end_event only the last partial chunk and the
// trailer are left, so the frame is on flash before end_event returns and
// the buffer is free for the next visit with nothing to wait for. Flash
// bits only clear, so the header is written with an all-ones length at
// open and finished at close without an erase.
//
// Sectors ahead of the writer are blanked on quiet steps, so the writes
// that happen during a visit are programs only, a few ms each.
//
// Nothing here blocks the loop task longer than one sector op, and the
// network never touches it: a shipper task publishes entries from a
// read-only mapping of the partition, and may block for as long as a bad
// link needs. The two share the pending table under a mutex.
//
// Layout: entries start on sector boundaries, header then frame bytes.
//   u32 magic "LBJ1"  u32 seq  u32 len  u32 crc  u32 state  u32 pad[3]
//   state: FFFFFFFF writing -> 0000FFFF complete -> 00000000 delivered.
//   len and crc (over magic, seq, len) are all-ones until close; the boot
//   scan only trusts an entry whose crc matches.
// Circular: an entry reserves up to MAX_ENTRY sectors ahead and evicts
// undelivered visits sector by sector only as it actually grows into them.
//
// ESP-IDF only — the replay harness never needs this.
#include <esp_log.h>
#include <esp_partition.h>
#include <esp_rom_crc.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>

class VisitStore {
 public:
  static const uint32_t SECTOR = 4096;
  static const uint32_t MAX_SECTORS = 256;   // 1 MB partition; the index is sized for it
  static const uint32_t MAX_ENTRY = 24;      // sectors a full frame (header + 36000 samples + trailer) spans
  static const uint32_t ERASE_AHEAD = 8;     // kept blank in front of the writer
  static const uint32_t CHUNK = 2048;        // bytes programmed per step while a visit is open
  static const uint32_t MAGIC = 0x314A424C;  // "LBJ1" little-endian
  static const uint32_t HEADER = 32;

  enum : uint32_t { WRITING = 0xFFFFFFFFu, COMPLETE = 0x0000FFFFu, DELIVERED = 0u };

  struct Header {
    uint32_t magic;
    uint32_t seq;
    uint32_t len;
    uint32_t crc;
    uint32_t state;
    uint32_t pad[3];
  };
  static_assert(sizeof(Header) == HEADER, "header layout");

  /** Publish `len` bytes; true once the client took them. Runs on the shipper task. */
  using PublishFn = std::function<bool(const char *data, size_t len)>;

  bool setup(const char *label, PublishFn publish) {
    part_ = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, label);
    if (part_ == nullptr) {
      ESP_LOGE(TAG, "No '%s' partition", label);
      return false;
    }
    const void *mapped = nullptr;
    if (esp_partition_mmap(part_, 0, part_->size, ESP_PARTITION_MMAP_DATA, &mapped, &mmap_) != ESP_OK) {
      ESP_LOGE(TAG, "Cannot map '%s'", label);
      return false;
    }
    map_ = static_cast<const uint8_t *>(mapped);
    nsec_ = part_->size / SECTOR;
    if (nsec_ > MAX_SECTORS) nsec_ = MAX_SECTORS;
    if (nsec_ < 3 * MAX_ENTRY) {
      ESP_LOGE(TAG, "'%s' too small: %u sectors", label, (unsigned) nsec_);
      part_ = nullptr;
      return false;
    }
    publish_ = std::move(publish);
    lock_ = xSemaphoreCreateMutex();
    scan_();
    xTaskCreate(run_, "visit_ship", 5120, this, 1, &task_);
    ESP_LOGI(TAG, "%u KB journal, %d pending, head at sector %u", (unsigned) (nsec_ * SECTOR / 1024),
             pending_count_, (unsigned) head_);
    return true;
  }

  /**
   * Start an entry for the visit being recorded into `frame`. Claims up to
   * MAX_ENTRY sectors ahead, so the shipper stays out of them, and writes
   * the header. One sector op at most.
   */
  bool open(const uint8_t *frame) {
    if (part_ == nullptr || wr_.open) return false;
    if (head_ + MAX_ENTRY > nsec_) head_ = 0;
    xSemaphoreTake(lock_, portMAX_DELAY);
    // A wrap must not land on the entry the shipper is reading out.
    if (in_flight_.len && overlaps_(head_, MAX_ENTRY, in_flight_)) {
      head_ = (in_flight_.off + HEADER + in_flight_.len + SECTOR - 1) / SECTOR;
      if (head_ + MAX_ENTRY > nsec_) head_ = 0;
    }
    reserved_from_ = head_;
    reserved_count_ = MAX_ENTRY;
    xSemaphoreGive(lock_);

    wr_ = Write{frame, head_, seq_next_++, 0, 0, true};
    prepare_sector_(head_);
    wr_.prepared = 1;
    Header h{MAGIC, wr_.seq, 0xFFFFFFFFu, 0xFFFFFFFFu, WRITING, {0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu}};
    set_blank_(head_, false);
    if (esp_partition_write(part_, head_ * SECTOR, &h, sizeof(h)) != ESP_OK) {
      abandon_("header write failed");
      return false;
    }
    wr_.written = 8;  // the frame's own header lands at close, once count is known
    return true;
  }

  bool is_open() const { return wr_.open; }

  /**
   * Program whole chunks of the frame that have arrived since the last
   * call; `frame_bytes` is how much of the frame is final (8 + 2 * samples).
   * With no entry open, keeps the sectors ahead blank instead.
   */
  void step(uint32_t frame_bytes) {
    if (part_ == nullptr) return;
    if (wr_.open) {
      if (frame_bytes - wr_.written >= CHUNK)
        write_(CHUNK);
      else
        erase_ahead_(wr_.sector + wr_.prepared);  // quiet step: blank the sectors the visit will grow into
      return;
    }
    erase_ahead_(head_);
  }

  /** The visit ended: write what is left, then finish the header. Synchronous, usually one sector. */
  bool close(uint32_t frame_len) {
    if (!wr_.open) return false;
    while (wr_.open && wr_.written < frame_len) write_(frame_len - wr_.written);
    if (!wr_.open) return false;
    uint32_t base = wr_.sector * SECTOR;
    // Frame header (magic + count) now that count is known, then ours.
    esp_err_t err = esp_partition_write(part_, base + HEADER, wr_.frame, 8);
    Header h{MAGIC, wr_.seq, frame_len, 0, COMPLETE, {0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu}};
    h.crc = crc_(h);
    if (err == ESP_OK) err = esp_partition_write(part_, base + offsetof(Header, len), &h.len, 12);
    if (err != ESP_OK) {
      abandon_("close failed");
      return false;
    }
    Entry e{base, frame_len, wr_.seq};
    xSemaphoreTake(lock_, portMAX_DELAY);
    if (pending_count_ < (int) MAX_SECTORS) pending_[pending_count_++] = e;
    reserved_count_ = 0;
    xSemaphoreGive(lock_);
    head_ = wr_.sector + sectors_(frame_len);
    if (head_ >= nsec_) head_ = 0;
    wr_.open = false;
    ESP_LOGI(TAG, "Journaled visit seq %u: %u bytes", (unsigned) e.seq, (unsigned) e.len);
    kick();
    return true;
  }

  /** Wake the shipper (on MQTT connect). */
  void kick() {
    if (task_) xTaskNotifyGive(task_);
  }

  int pending() const { return pending_count_; }

  // Diagnostics.
  uint32_t sectors() const { return nsec_; }
  uint32_t head_sector() const { return head_; }
  uint32_t bytes_written() const { return wr_.open ? wr_.written : 0; }
  int blank_sectors() const {
    int c = 0;
    for (uint32_t i = 0; i < nsec_; i++) c += blank_(i) ? 1 : 0;
    return c;
  }

 private:
  static constexpr const char *TAG = "VS";

  struct Entry {
    uint32_t off;  // bytes from partition start
    uint32_t len;  // frame bytes after the header
    uint32_t seq;
  };

  struct Write {
    const uint8_t *frame;
    uint32_t sector;    // first sector of the entry
    uint32_t seq;
    uint32_t written;   // frame bytes on flash so far
    uint32_t prepared;  // sectors of the entry made ours so far
    bool open;
  };

  static uint32_t sectors_(uint32_t frame_len) { return (HEADER + frame_len + SECTOR - 1) / SECTOR; }
  static uint32_t crc_(const Header &h) { return esp_rom_crc32_le(0, reinterpret_cast<const uint8_t *>(&h), 12); }

  static bool overlaps_(uint32_t sector, uint32_t count, const Entry &e) {
    uint32_t a = sector * SECTOR, b = (sector + count) * SECTOR;
    return e.off < b && e.off + HEADER + e.len > a;
  }

  bool blank_(uint32_t s) const { return blank_bits_[s / 8] & (1u << (s % 8)); }
  void set_blank_(uint32_t s, bool v) {
    if (v)
      blank_bits_[s / 8] |= (1u << (s % 8));
    else
      blank_bits_[s / 8] &= ~(1u << (s % 8));
  }

  /** Whole-sector check against the mapping; boot only. */
  bool reads_blank_(uint32_t s) const {
    const uint32_t *p = reinterpret_cast<const uint32_t *>(map_ + s * SECTOR);
    for (uint32_t i = 0; i < SECTOR / 4; i++)
      if (p[i] != 0xFFFFFFFFu) return false;
    return true;
  }

  void scan_() {
    memset(blank_bits_, 0, sizeof(blank_bits_));
    pending_count_ = 0;
    uint32_t max_seq = 0, after_max = 0;
    bool any = false;
    for (uint32_t s = 0; s < nsec_;) {
      const Header *h = reinterpret_cast<const Header *>(map_ + s * SECTOR);
      bool entry = h->magic == MAGIC && h->len != 0xFFFFFFFFu && h->crc == crc_(*h) &&
                   s + sectors_(h->len) <= nsec_;
      if (!entry) {
        set_blank_(s, reads_blank_(s));
        s++;
        continue;
      }
      if (h->state == COMPLETE && pending_count_ < (int) MAX_SECTORS)
        pending_[pending_count_++] = Entry{s * SECTOR, h->len, h->seq};
      if (!any || h->seq > max_seq) {
        max_seq = h->seq;
        after_max = s + sectors_(h->len);
        any = true;
      }
      s += sectors_(h->len);
    }
    seq_next_ = any ? max_seq + 1 : 1;
    head_ = (any && after_max < nsec_) ? after_max : 0;
    sort_pending_();
  }

  void sort_pending_() {
    for (int i = 1; i < pending_count_; i++) {
      Entry e = pending_[i];
      int j = i - 1;
      while (j >= 0 && pending_[j].seq > e.seq) {
        pending_[j + 1] = pending_[j];
        j--;
      }
      pending_[j + 1] = e;
    }
  }

  int pending_at_(uint32_t sector, uint32_t count) const {
    for (int i = 0; i < pending_count_; i++)
      if (overlaps_(sector, count, pending_[i])) return i;
    return -1;
  }

  void remove_pending_(int i) {
    for (int j = i; j + 1 < pending_count_; j++) pending_[j] = pending_[j + 1];
    pending_count_--;
  }

  /** Make sector `s` ours: drop whatever undelivered visit sat there, blank it. */
  void prepare_sector_(uint32_t s) {
    xSemaphoreTake(lock_, portMAX_DELAY);
    for (int i; (i = pending_at_(s, 1)) >= 0;) {
      ESP_LOGW(TAG, "Journal full: dropping undelivered visit seq %u", (unsigned) pending_[i].seq);
      remove_pending_(i);
    }
    xSemaphoreGive(lock_);
    if (!blank_(s)) erase_(s);
  }

  void erase_(uint32_t s) {
    if (esp_partition_erase_range(part_, s * SECTOR, SECTOR) == ESP_OK) set_blank_(s, true);
  }

  /** Program the next `n` frame bytes; sectors are prepared as the entry grows into them. */
  void write_(uint32_t n) {
    uint32_t off = wr_.sector * SECTOR + HEADER + wr_.written;
    uint32_t last = (off + n - 1) / SECTOR;
    for (uint32_t s = wr_.sector + wr_.prepared; s <= last; s++) {
      prepare_sector_(s);
      wr_.prepared = s - wr_.sector + 1;
    }
    for (uint32_t s = wr_.sector; s <= last; s++) set_blank_(s, false);
    if (esp_partition_write(part_, off, wr_.frame + wr_.written, n) != ESP_OK) {
      abandon_("write failed");
      return;
    }
    wr_.written += n;
  }

  void abandon_(const char *why) {
    ESP_LOGE(TAG, "Visit seq %u lost: %s", (unsigned) wr_.seq, why);
    xSemaphoreTake(lock_, portMAX_DELAY);
    reserved_count_ = 0;
    xSemaphoreGive(lock_);
    head_ = wr_.sector + (wr_.prepared ? wr_.prepared : 1);
    if (head_ >= nsec_) head_ = 0;
    wr_.open = false;
  }

  /** Keep the sectors in front of `from` blank, never into undelivered visits. One erase at most. */
  void erase_ahead_(uint32_t from) {
    for (uint32_t j = 0; j < ERASE_AHEAD; j++) {
      uint32_t s = (from + j) % nsec_;
      if (blank_(s)) continue;
      xSemaphoreTake(lock_, portMAX_DELAY);
      bool taken = pending_at_(s, 1) >= 0 || (in_flight_.len && overlaps_(s, 1, in_flight_));
      xSemaphoreGive(lock_);
      if (taken) return;
      erase_(s);
      return;
    }
  }

  /** Oldest pending entry the writer is not about to grow into; becomes in-flight. */
  bool next_to_ship_(Entry *out) {
    bool found = false;
    xSemaphoreTake(lock_, portMAX_DELAY);
    for (int i = 0; i < pending_count_; i++) {
      if (reserved_count_ && overlaps_(reserved_from_, reserved_count_, pending_[i])) continue;
      *out = pending_[i];
      in_flight_ = pending_[i];
      found = true;
      break;
    }
    xSemaphoreGive(lock_);
    return found;
  }

  /** Delivered: drop it from the table and clear its state word, unless the sector moved on. */
  void delivered_(const Entry &e) {
    xSemaphoreTake(lock_, portMAX_DELAY);
    in_flight_ = Entry{};
    for (int i = 0; i < pending_count_; i++) {
      if (pending_[i].off == e.off && pending_[i].seq == e.seq) {
        remove_pending_(i);
        break;
      }
    }
    const Header *h = reinterpret_cast<const Header *>(map_ + e.off);
    if (h->magic == MAGIC && h->seq == e.seq) {
      uint32_t zero = DELIVERED;
      esp_partition_write(part_, e.off + offsetof(Header, state), &zero, 4);
    }
    xSemaphoreGive(lock_);
  }

  void ship_() {
    Entry e;
    while (next_to_ship_(&e)) {
      bool ok = publish_(reinterpret_cast<const char *>(map_ + e.off + HEADER), e.len);
      if (!ok) {
        xSemaphoreTake(lock_, portMAX_DELAY);
        in_flight_ = Entry{};
        xSemaphoreGive(lock_);
        return;
      }
      delivered_(e);
      ESP_LOGI(TAG, "Shipped visit seq %u (%u bytes)", (unsigned) e.seq, (unsigned) e.len);
    }
  }

  static void run_(void *arg) {
    auto *self = static_cast<VisitStore *>(arg);
    for (;;) {
      // Kicked on close and on MQTT connect; the poll covers a publish that
      // failed for a reason nobody signals, and entries a close just freed.
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(30000));
      self->ship_();
    }
  }

  const esp_partition_t *part_ = nullptr;
  esp_partition_mmap_handle_t mmap_ = 0;
  const uint8_t *map_ = nullptr;
  uint32_t nsec_ = 0;
  uint32_t head_ = 0;
  uint32_t seq_next_ = 1;
  uint8_t blank_bits_[MAX_SECTORS / 8];  // sectors known to read all-FF
  Entry pending_[MAX_SECTORS];
  int pending_count_ = 0;
  Write wr_{};
  PublishFn publish_;
  SemaphoreHandle_t lock_ = nullptr;
  TaskHandle_t task_ = nullptr;
  Entry in_flight_{};           // what the shipper is publishing; its sectors are off limits
  uint32_t reserved_from_ = 0;  // window the open entry may grow into; the shipper stays out
  uint32_t reserved_count_ = 0;
};

inline VisitStore &get_visit_store() {
  static VisitStore instance;
  return instance;
}
