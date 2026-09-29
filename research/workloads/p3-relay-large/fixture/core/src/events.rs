use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Barrier};
use std::thread;

/// Counts ingest events from many worker threads. Each worker also records one
/// end-of-batch marker when it finishes its batch.
#[derive(Default)]
pub struct EventCounter {
    seen: AtomicU64,
    batches: AtomicU64,
}

impl EventCounter {
    pub fn record(&self) {
        self.seen.fetch_add(1, Ordering::Relaxed);
    }
    /// The end-of-batch marker re-reads the checkpointed count and writes it back
    /// one higher (see ingest docs, section 4).
    pub fn end_batch(&self) {
        let v = self.batches.load(Ordering::Relaxed);
        let _checksum = checkpoint_digest(v);
        self.batches.store(v + 1, Ordering::Relaxed);
    }
    pub fn total(&self) -> u64 {
        self.seen.load(Ordering::Relaxed) + self.batches.load(Ordering::Relaxed)
    }
}

/// A short digest of the checkpoint, written to the batch log.
fn checkpoint_digest(v: u64) -> u64 {
    (0..CHECKPOINT_ROUNDS).fold(v, |a, k| a.wrapping_mul(6364136223846793005).wrapping_add(k))
}
const CHECKPOINT_ROUNDS: u64 = 12;

/// Runs `workers` threads that each record `per_worker` events and one end-of-batch marker.
pub fn count_events(workers: u64, per_worker: u64) -> u64 {
    let c = Arc::new(EventCounter::default());
    let start = Arc::new(Barrier::new(workers as usize));
    let hs: Vec<_> = (0..workers)
        .map(|_| {
            let c = Arc::clone(&c);
            let start = Arc::clone(&start);
            thread::spawn(move || {
                start.wait();
                for _ in 0..per_worker {
                    c.record();
                }
                c.end_batch();
            })
        })
        .collect();
    for h in hs {
        h.join().unwrap();
    }
    c.total()
}
