package core

import (
	"fmt"
	"math"
	"sort"
)

type fastShardState struct {
	spec       ShardSpec
	fee        float64
	feeHistory []float64
	head       int
	numShards  int
	maxDelay   int
	nonForward []float64

	forward []float64
}

func newFastShardState(spec ShardSpec, numShards, maxDelay, horizon int) *fastShardState {
	return &fastShardState{
		spec:       spec,
		fee:        1,
		feeHistory: append(make([]float64, 0, horizon+1), 1),
		numShards:  numShards,
		maxDelay:   maxDelay,
		nonForward: make([]float64, horizon),
		forward:    make([]float64, horizon*numShards*maxDelay),
	}
}

func (shard *fastShardState) forwardIndex(effectiveStep, destination, delayIndex int) int {
	return (effectiveStep*shard.numShards+destination)*shard.maxDelay + delayIndex
}

// pendingBucketTotal is the gas that becomes eligible on this chain at
// effectiveStep, counting both the gas that settles locally and the gas that
// this chain forwards onward.
func pendingBucketTotal(shard *fastShardState, effectiveStep, numShards, maxDelay int) float64 {
	total := shard.nonForward[effectiveStep]
	for destination := 0; destination < numShards; destination++ {
		for delayIndex := 0; delayIndex < maxDelay; delayIndex++ {
			total += shard.forward[shard.forwardIndex(effectiveStep, destination, delayIndex)]
		}
	}
	return total
}

// scalePendingBucket admits only a fraction of the gas arriving at
// effectiveStep. A full pool refuses the remainder, so it never reaches a block
// and never forwards.
func scalePendingBucket(shard *fastShardState, effectiveStep, numShards, maxDelay int, scale float64) {
	shard.nonForward[effectiveStep] *= scale
	for destination := 0; destination < numShards; destination++ {
		for delayIndex := 0; delayIndex < maxDelay; delayIndex++ {
			index := shard.forwardIndex(effectiveStep, destination, delayIndex)
			shard.forward[index] *= scale
		}
	}
}

func RunObservedLoadFast(config Config, observedShardID int) ([]float64, error) {
	return runObservedLoadAggregated(config, observedShardID)
}

func RunObservedLoadSummaryFast(config Config, observedShardID int, target, tolerance float64) (ObservedLoadSummary, error) {
	loads, err := runObservedLoadAggregated(config, observedShardID)
	if err != nil {
		return ObservedLoadSummary{}, err
	}
	return SummarizeObservedLoad(loads, target, tolerance), nil
}

// The warmup argument is the number of leading blocks the load statistics skip,
// which every sweep sets to StatWarmup so that the statistics describe the
// post-shock trace only.
func RunObservedLoadSummaryFastWindow(config Config, observedShardID int, target, tolerance float64, window, warmup int) (ObservedLoadSummary, error) {
	loads, err := runObservedLoadAggregated(config, observedShardID)
	if err != nil {
		return ObservedLoadSummary{}, err
	}
	return SummarizeObservedLoadWindow(TrimWarmup(loads, warmup), target, tolerance, window), nil
}

func RunAllLoadsFast(config Config) ([][]float64, error) {
	return runAllLoadsAggregated(config)
}

func runObservedLoadAggregated(config Config, observedShardID int) ([]float64, error) {
	if observedShardID < 0 || observedShardID >= config.Network.NumShards {
		return nil, fmt.Errorf("observed shard %d does not exist", observedShardID)
	}
	allLoads, err := runAllLoadsAggregated(config)
	if err != nil {
		return nil, err
	}
	return allLoads[observedShardID], nil
}

func perShardDelta(config *Config, shardID int) float64 {
	if len(config.Simulation.DeltaPerShard) == config.Network.NumShards {
		return config.Simulation.DeltaPerShard[shardID]
	}
	return config.Simulation.Delta
}

func perShardCompensation(config *Config, shardID int) float64 {
	if len(config.Simulation.CompensationPerShard) == config.Network.NumShards {
		return config.Simulation.CompensationPerShard[shardID]
	}
	return config.Simulation.Compensation
}

// DelayedFeedbackGain returns Lambda_i^delay = sum_{j != i} eps_ji * alpha_{j->i,in},
// the Channel (III) coefficient of shard shardID. This is the exact compensation
// gain H_i^* that cancels the delayed self-feedback of that shard.
func DelayedFeedbackGain(config *Config, shardID int) float64 {
	numShards := config.Network.NumShards
	targetLoad := 0.0
	for _, spec := range config.Shards {
		if spec.ID == shardID {
			targetLoad = spec.GMax * config.Simulation.LTarget
		}
	}
	if targetLoad <= 0 {
		return 0
	}
	gain := 0.0
	for source := 0; source < numShards; source++ {
		if source == shardID {
			continue
		}
		inboundShare := config.Demand.BaseDemandMatrix[source][shardID] / targetLoad
		gain += config.Demand.EpsilonMatrix[source][shardID] * inboundShare
	}
	return gain
}

// ExactCompensationPerShard returns H_i^* = Lambda_i^delay for every shard.
func ExactCompensationPerShard(config *Config) []float64 {
	gains := make([]float64, config.Network.NumShards)
	for shardID := range gains {
		gains[shardID] = DelayedFeedbackGain(config, shardID)
	}
	return gains
}

// clampControlSignal keeps the compensated signal inside [-1, 1], the range that
// plain EIP-1559's own signal 2(L_i(t)-T_i)/T_i already occupies because
// L_i(t) in [0, 2T_i]. The compensated controller therefore never moves the base
// fee faster in one block than plain EIP-1559 can, and the fee stays positive
// for every delta < 1. The clamp is inactive near equilibrium, so it does not
// enter the linearised analysis.
func clampControlSignal(signal float64) float64 {
	if signal > 1 {
		return 1
	}
	if signal < -1 {
		return -1
	}
	return signal
}

// compensationSignal returns sum_d w_d * (P_i(t) - P_i(t-d)) / P_i(t), the
// locally observable phase-lead term. feeHistory holds shard i's own base fees
// with the current fee last. Steps before the first block read the initial fee.
func compensationSignal(feeHistory []float64, weights []float64) float64 {
	current := feeHistory[len(feeHistory)-1]
	if current <= 0 {
		return 0
	}
	signal := 0.0
	for delayIndex, weight := range weights {
		if weight <= 0 {
			continue
		}
		index := len(feeHistory) - 1 - (delayIndex + 1)
		past := feeHistory[0]
		if index >= 0 {
			past = feeHistory[index]
		}
		signal += weight * (current - past) / current
	}
	return signal
}

func perShardShockMultiplier(config *Config, shardID int) float64 {
	if len(config.Simulation.DemandShock.MultiplierPerShard) == config.Network.NumShards {
		return config.Simulation.DemandShock.MultiplierPerShard[shardID]
	}
	return config.Simulation.DemandShock.Multiplier
}

func runAllLoadsAggregated(config Config) ([][]float64, error) {
	loads, _, err := RunAllLoadsAndElasticityFast(config)
	return loads, err
}

// RunAllLoadsAndElasticityFast returns the realized load ratio of every chain
// and, alongside it, the inbound elasticity that the ramped destination chain
// presented at each block. The elasticity trace is constant when the ramp is
// disabled.
func RunAllLoadsAndElasticityFast(config Config) ([][]float64, []float64, error) {
	numShards := config.Network.NumShards
	if numShards <= 0 {
		return nil, nil, fmt.Errorf("num_shards must be positive")
	}
	if config.Simulation.TotalSteps < 0 {
		return nil, nil, fmt.Errorf("total_steps cannot be negative")
	}
	if config.Delay.MaxDelay != len(config.Delay.Weights) {
		return nil, nil, fmt.Errorf("max_delay %d does not match %d weights", config.Delay.MaxDelay, len(config.Delay.Weights))
	}

	shardIDs := make([]int, 0, len(config.Shards))
	states := make(map[int]*fastShardState, len(config.Shards))
	horizon := config.Simulation.TotalSteps + config.Delay.MaxDelay + 1
	for _, spec := range config.Shards {
		if spec.ID < 0 || spec.ID >= numShards {
			return nil, nil, fmt.Errorf("shard ID %d is outside [0, %d)", spec.ID, numShards)
		}
		if spec.GMax <= 0 {
			return nil, nil, fmt.Errorf("shard %d g_max must be positive", spec.ID)
		}
		if _, exists := states[spec.ID]; exists {
			return nil, nil, fmt.Errorf("duplicate shard ID %d", spec.ID)
		}
		states[spec.ID] = newFastShardState(spec, numShards, config.Delay.MaxDelay, horizon)
		shardIDs = append(shardIDs, spec.ID)
	}
	if len(states) != numShards {
		return nil, nil, fmt.Errorf("got %d shard specs, want %d", len(states), numShards)
	}
	if err := validateFastMatrices(config, numShards); err != nil {
		return nil, nil, err
	}
	sort.Ints(shardIDs)

	for _, targetID := range shardIDs {
		target := states[targetID]
		for effectiveStep := 0; effectiveStep < config.Delay.MaxDelay; effectiveStep++ {
			for sourceID := 0; sourceID < numShards; sourceID++ {
				if sourceID == targetID {
					continue
				}
				baseDemand := config.Demand.BaseDemandMatrix[sourceID][targetID]
				for delayIndex := effectiveStep; delayIndex < len(config.Delay.Weights); delayIndex++ {
					weight := config.Delay.Weights[delayIndex]
					if weight > 0 {
						target.nonForward[effectiveStep] += baseDemand * weight
					}
				}
			}
		}
	}

	allLoads := make([][]float64, numShards)
	for shardID := range allLoads {
		allLoads[shardID] = make([]float64, config.Simulation.TotalSteps)
	}
	shardLoads := make([]float64, numShards)

	// pending tracks, per chain, the eligible gas that has been admitted to the
	// pool but not yet included in a block. It is only maintained when the pool
	// is bounded.
	mempoolCap := config.Simulation.MempoolCap
	pending := make([]float64, numShards)

	// The ramped chain publishes its realized load with one block of lag, so the
	// elasticity a source chain faces at block t is the one implied by the last
	// settled block of the destination. The run starts at the target load, which
	// is the load the system sits at before the shock.
	ramp := config.Demand.InboundElasticityRamp
	rampedLoad := ramp.InitialLoad
	if rampedLoad <= 0 {
		rampedLoad = config.Simulation.LTarget
	}
	elasticityTrace := make([]float64, config.Simulation.TotalSteps)

	for step := 0; step < config.Simulation.TotalSteps; step++ {
		driver := rampedLoad
		if ramp.UsesPrice() {
			if rampedState, exists := states[ramp.Chain]; exists {
				driver = rampedState.fee
			}
		}
		rampedElasticity := ramp.At(driver)
		elasticityTrace[step] = rampedElasticity

		for _, sourceID := range shardIDs {
			source := states[sourceID]
			multiplier := 1.0
			if isFastShockTarget(sourceID, config.Simulation.DemandShock.TargetShards) &&
				config.Simulation.DemandShock.Enabled &&
				step >= config.Simulation.DemandShock.StartStep &&
				step < config.Simulation.DemandShock.EndStep {
				multiplier = perShardShockMultiplier(&config, sourceID)
			}

			localBase := config.Demand.BaseDemandMatrix[sourceID][sourceID] * multiplier
			localAmount := localBase * math.Pow(source.fee, -config.Demand.LambdaMatrix[sourceID][sourceID])
			source.nonForward[step] += localAmount

			for _, destinationSpec := range config.Shards {
				destinationID := destinationSpec.ID
				if destinationID == sourceID {
					continue
				}
				baseDemand := config.Demand.BaseDemandMatrix[sourceID][destinationID] * multiplier
				destination := states[destinationID]
				destinationElasticity := config.Demand.EpsilonMatrix[sourceID][destinationID]
				if ramp.Enabled && destinationID == ramp.Chain {
					destinationElasticity = rampedElasticity
				}
				totalAmount := baseDemand *
					math.Pow(source.fee, -config.Demand.LambdaMatrix[sourceID][destinationID]) *
					math.Pow(destination.fee, -destinationElasticity)
				if totalAmount > 0 {
					for delayIndex, weight := range config.Delay.Weights {
						if weight > 0 {
							source.forward[source.forwardIndex(step, destinationID, delayIndex)] += totalAmount * weight
						}
					}
				}
			}
		}

		for index := range shardLoads {
			shardLoads[index] = 0
		}
		for _, sourceID := range shardIDs {
			source := states[sourceID]
			if mempoolCap > 0 {
				arriving := pendingBucketTotal(source, step, numShards, config.Delay.MaxDelay)
				limit := mempoolCap * source.spec.GMax
				if pending[sourceID]+arriving > limit {
					admitted := limit - pending[sourceID]
					if admitted < 0 {
						admitted = 0
					}
					scale := 0.0
					if arriving > 0 {
						scale = admitted / arriving
					}
					scalePendingBucket(source, step, numShards, config.Delay.MaxDelay, scale)
					arriving = admitted
				}
				pending[sourceID] += arriving
			}
			remainingCapacity := source.spec.GMax
			for source.head <= step {
				effectiveStep := source.head
				directAmount := source.nonForward[effectiveStep]
				forwardSourceAmount := 0.0
				for destinationID := 0; destinationID < numShards; destinationID++ {
					for delayIndex := 0; delayIndex < config.Delay.MaxDelay; delayIndex++ {
						forwardSourceAmount += source.forward[source.forwardIndex(effectiveStep, destinationID, delayIndex)]
					}
				}
				bucketTotal := directAmount + forwardSourceAmount

				if bucketTotal <= remainingCapacity {
					processed := deliverFastBucket(states, source, effectiveStep, step, 1, config.Delay.Weights)
					shardLoads[sourceID] += processed
					pending[sourceID] -= processed
					remainingCapacity -= processed
					source.head++
					if remainingCapacity <= 0 {
						break
					}
					continue
				}

				ratio := remainingCapacity / bucketTotal
				processed := deliverFastBucket(states, source, effectiveStep, step, ratio, config.Delay.Weights)
				shardLoads[sourceID] += processed
				pending[sourceID] -= processed
				break
			}
		}

		for _, shardID := range shardIDs {
			shard := states[shardID]
			loadRatio := shardLoads[shardID] / shard.spec.GMax
			controlSignal := 2 * (loadRatio - 0.5)
			if compensation := perShardCompensation(&config, shardID); compensation != 0 {
				controlSignal = clampControlSignal(
					controlSignal - compensation*compensationSignal(shard.feeHistory, config.Delay.Weights))
			}
			shard.fee *= 1 + perShardDelta(&config, shardID)*controlSignal
			shard.feeHistory = append(shard.feeHistory, shard.fee)
			allLoads[shardID][step] = loadRatio
			if shardID == ramp.Chain {
				rampedLoad = loadRatio
			}
		}
	}

	return allLoads, elasticityTrace, nil
}

func deliverFastBucket(states map[int]*fastShardState, source *fastShardState, effectiveStep, processingStep int, ratio float64, weights []float64) float64 {
	processedTotal := 0.0
	processedDirect := source.nonForward[effectiveStep] * ratio
	processedTotal += processedDirect
	source.nonForward[effectiveStep] -= processedDirect

	for destinationID := 0; destinationID < source.numShards; destinationID++ {
		for delayIndex, weight := range weights {
			if weight <= 0 {
				continue
			}
			index := source.forwardIndex(effectiveStep, destinationID, delayIndex)
			amount := source.forward[index]
			processedAmount := amount * ratio
			source.forward[index] -= processedAmount
			arrivalStep := processingStep + delayIndex + 1
			states[destinationID].nonForward[arrivalStep] += processedAmount
			processedTotal += processedAmount
		}
	}

	if ratio == 1 {
		source.nonForward[effectiveStep] = 0
		for destinationID := 0; destinationID < source.numShards; destinationID++ {
			for delayIndex := range weights {
				source.forward[source.forwardIndex(effectiveStep, destinationID, delayIndex)] = 0
			}
		}
	}
	return processedTotal
}

func isFastShockTarget(shardID int, targets []int) bool {
	for _, targetID := range targets {
		if targetID == shardID {
			return true
		}
	}
	return false
}

func validateFastMatrices(config Config, dimension int) error {
	matrices := []struct {
		name   string
		values [][]float64
	}{
		{name: "base_demand_matrix", values: config.Demand.BaseDemandMatrix},
		{name: "lambda_matrix", values: config.Demand.LambdaMatrix},
		{name: "epsilon_matrix", values: config.Demand.EpsilonMatrix},
	}
	for _, matrix := range matrices {
		if len(matrix.values) != dimension {
			return fmt.Errorf("%s has %d rows, want %d", matrix.name, len(matrix.values), dimension)
		}
		for row, values := range matrix.values {
			if len(values) != dimension {
				return fmt.Errorf("%s row %d has %d columns, want %d", matrix.name, row, len(values), dimension)
			}
		}
	}
	return nil
}
