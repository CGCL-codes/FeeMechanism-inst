package core

import (
	"fmt"
	"math"
	"sort"
)

type ObservedLoadSummary struct {
	FinalLoad     float64
	AverageLoad   float64
	LoadStd       float64
	LoadInflation float64
	Converged     bool

	// FullBlockFraction is the fraction of blocks whose realized load reaches
	// the gas limit. Under stable operation it is zero, and it rises as the
	// load concentrates at the two extremes.
	FullBlockFraction float64
}

// fullBlockTolerance absorbs the floating-point residue left by the
// proportional fill of a partially included bucket.
const fullBlockTolerance = 1e-9

func RunObservedLoad(config Config, observedShardID int) ([]float64, error) {
	simulation := NewSimulation(config)
	observedShard, ok := simulation.Shards[observedShardID]
	if !ok {
		return nil, fmt.Errorf("observed shard %d does not exist", observedShardID)
	}

	simulation.GenerateInitialLoad()

	shardIDs := make([]int, 0, len(simulation.Shards))
	for shardID := range simulation.Shards {
		shardIDs = append(shardIDs, shardID)
	}
	sort.Ints(shardIDs)

	loads := make([]float64, 0, config.Simulation.TotalSteps)
	for step := 0; step < config.Simulation.TotalSteps; step++ {
		for _, shardID := range shardIDs {
			shard := simulation.Shards[shardID]
			demand := shard.GenerateDemand(step, &simulation.Config)
			shard.PendingLoad = append(shard.PendingLoad, demand...)
		}

		shardLoads := make(map[int]float64, len(shardIDs))
		for _, shardID := range shardIDs {
			shard := simulation.Shards[shardID]
			processed := shard.AbstractLoad(step)
			for _, load := range processed {
				if load.Forward {
					targetShard := simulation.Shards[load.ShardTo]
					load.Forward = false
					load.EffectiveStep = step + load.DelayedStep
					targetShard.PendingLoad = append(targetShard.PendingLoad, load)
				}
				shardLoads[shardID] += load.Amount
			}
		}

		for _, shardID := range shardIDs {
			shard := simulation.Shards[shardID]
			shard.UpdateFee(shardLoads[shardID] / shard.Spec.GMax)
		}

		loads = append(loads, shardLoads[observedShardID]/observedShard.Spec.GMax)
	}

	return loads, nil
}

func SummarizeObservedLoad(loads []float64, target, tolerance float64) ObservedLoadSummary {
	if len(loads) == 0 {
		return ObservedLoadSummary{}
	}

	sum := 0.0
	for _, load := range loads {
		sum += load
	}
	average := sum / float64(len(loads))

	std := 0.0
	if len(loads) > 1 {
		squaredDeviation := 0.0
		for _, load := range loads {
			difference := load - average
			squaredDeviation += difference * difference
		}
		std = math.Sqrt(squaredDeviation / float64(len(loads)-1))
	}

	fullBlocks := 0
	for _, load := range loads {
		if load >= 1-fullBlockTolerance {
			fullBlocks++
		}
	}

	finalLoad := loads[len(loads)-1]
	return ObservedLoadSummary{
		FinalLoad:         finalLoad,
		AverageLoad:       average,
		LoadStd:           std,
		LoadInflation:     (average - target) / target,
		Converged:         withinOpenTolerance(finalLoad, target, tolerance),
		FullBlockFraction: float64(fullBlocks) / float64(len(loads)),
	}
}

func withinOpenTolerance(load, target, tolerance float64) bool {
	lowerBound := target - tolerance
	upperBound := target + tolerance
	return load > lowerBound && load < upperBound
}

// StatWarmup is the number of leading blocks that the realized-load statistics
// exclude. Every experiment injects its one-block demand shock at block 100 of
// a 50,100-block run, so the statistics cover the 50,000 post-shock blocks.
const StatWarmup = 100

// TrimWarmup drops the pre-shock blocks from a realized-load trace. The final
// load and the convergence window both read the tail of the trace, so trimming
// the head changes the load statistics without changing the verdict.
func TrimWarmup(loads []float64, warmup int) []float64 {
	if warmup <= 0 || warmup >= len(loads) {
		return loads
	}
	return loads[warmup:]
}

func SummarizeObservedLoadWindow(loads []float64, target, tolerance float64, window int) ObservedLoadSummary {
	summary := SummarizeObservedLoad(loads, target, tolerance)
	summary.Converged = false
	if window <= 0 || len(loads) < window {
		return summary
	}
	for _, load := range loads[len(loads)-window:] {
		if !withinOpenTolerance(load, target, tolerance) {
			return summary
		}
	}
	summary.Converged = true
	return summary
}
