export interface Job { jobId: string; startedAt: Date; rows: number }

export function describe(job: Job): string {
  return `${job.id}: ${job.rows} rows since ${stamp(job.startedAt)}`;
}

/** YYYY-MM-DD in UTC. */
export function stamp(d: Date): string {
  const mm = String(d.getUTCMonth()).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${d.getUTCFullYear()}-${mm}-${dd}`;
}
