#ifndef LAB4_SMP_STATS_H
#define LAB4_SMP_STATS_H

#include "param.h"

// Shared, read-only diagnostic ABI. Include types.h before this header.
// Counters belong to physical hart IDs, even when processes migrate.
struct smp_stats {
  uint64 online_mask;
  uint64 dispatches[NCPU];
  uint64 user_ticks[NCPU];
  uint64 free_pages;
};

#endif
