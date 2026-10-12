package core

import "sort"

type Shard struct {
	Spec        ShardSpec
	Simulation  *Simulation
	Load        []float64
	Fee         []float64
	PendingLoad []*Load
}

type Load struct {
	ShardFrom     int
	ShardTo       int
	Amount        float64
	Step          int
	DelayedStep   int
	EffectiveStep int
	Forward       bool
}

func NewShard(spec ShardSpec) *Shard {
	shard := &Shard{
		Spec:        spec,
		Load:        make([]float64, 0, 100000),
		Fee:         make([]float64, 0, 100000),
		PendingLoad: make([]*Load, 0, 100000),
	}

	shard.Fee = append(shard.Fee, 1.0)

	return shard
}

func (s *Shard) UpdateFee(load float64) {
	if len(s.Fee) == 0 {
		s.Fee = append(s.Fee, 1.0)
	}

	delta := perShardDelta(&s.Simulation.Config, s.Spec.ID)
	controlSignal := 2 * (load - 0.5)
	if compensation := perShardCompensation(&s.Simulation.Config, s.Spec.ID); compensation != 0 {
		controlSignal = clampControlSignal(
			controlSignal - compensation*compensationSignal(s.Fee, s.Simulation.Config.Delay.Weights))
	}
	fee := s.Fee[len(s.Fee)-1] * (1 + delta*controlSignal)
	s.Fee = append(s.Fee, fee)
}

func (s *Shard) AbstractLoad(step int) []*Load {

	var candidateLoads []*Load
	var candidateIndices []int

	for i, load := range s.PendingLoad {
		if load != nil && load.EffectiveStep <= step {

			loadCopy := *load
			candidateLoads = append(candidateLoads, &loadCopy)
			candidateIndices = append(candidateIndices, i)
		}
	}

	indices := make([]int, len(candidateLoads))
	for i := range indices {
		indices[i] = i
	}

	sort.Slice(indices, func(i, j int) bool {
		return candidateLoads[indices[i]].EffectiveStep < candidateLoads[indices[j]].EffectiveStep
	})

	sortedLoads := make([]*Load, len(candidateLoads))
	sortedIndices := make([]int, len(candidateLoads))
	for i, idx := range indices {
		sortedLoads[i] = candidateLoads[idx]
		sortedIndices[i] = candidateIndices[idx]
	}

	totalAmount := 0.0
	for _, load := range sortedLoads {
		totalAmount += load.Amount
	}

	gmax := s.Spec.GMax

	if totalAmount <= gmax {

		sort.Sort(sort.Reverse(sort.IntSlice(sortedIndices)))
		for _, idx := range sortedIndices {
			s.PendingLoad = append(s.PendingLoad[:idx], s.PendingLoad[idx+1:]...)
		}
		return sortedLoads
	}

	var result []*Load
	var toRemove []int
	remainingCapacity := gmax

	stepGroups := make(map[int][]*Load)
	stepIndices := make(map[int][]int)
	for i, load := range sortedLoads {
		stepGroups[load.EffectiveStep] = append(stepGroups[load.EffectiveStep], load)
		stepIndices[load.EffectiveStep] = append(stepIndices[load.EffectiveStep], sortedIndices[i])
	}

	var sortedSteps []int
	for step := range stepGroups {
		sortedSteps = append(sortedSteps, step)
	}
	sort.Ints(sortedSteps)

	for _, effectiveStep := range sortedSteps {
		loads := stepGroups[effectiveStep]
		indices := stepIndices[effectiveStep]

		stepTotalAmount := 0.0
		for _, load := range loads {
			stepTotalAmount += load.Amount
		}

		if stepTotalAmount <= remainingCapacity {

			for _, load := range loads {
				result = append(result, load)
			}

			toRemove = append(toRemove, indices...)
			remainingCapacity -= stepTotalAmount
		} else {

			ratio := remainingCapacity / stepTotalAmount

			for i, load := range loads {
				originalIdx := indices[i]
				originalLoad := s.PendingLoad[originalIdx]

				partialLoad := &Load{
					ShardFrom:     load.ShardFrom,
					ShardTo:       load.ShardTo,
					Amount:        load.Amount * ratio,
					Step:          load.Step,
					DelayedStep:   load.DelayedStep,
					EffectiveStep: load.EffectiveStep,
					Forward:       load.Forward,
				}
				result = append(result, partialLoad)

				originalLoad.Amount -= partialLoad.Amount
				if originalLoad.Amount <= 0 {
					toRemove = append(toRemove, originalIdx)
				}
			}

			break
		}

		if remainingCapacity <= 0 {
			break
		}
	}

	sort.Sort(sort.Reverse(sort.IntSlice(toRemove)))
	for _, idx := range toRemove {
		s.PendingLoad = append(s.PendingLoad[:idx], s.PendingLoad[idx+1:]...)
	}

	return result
}
