package core

import (
	"math"
)

func (s *Shard) GenerateDemand(step int, config *Config) []*Load {
	isShockTarget := false
	for _, targetShardID := range config.Simulation.DemandShock.TargetShards {
		if targetShardID == s.Spec.ID {
			isShockTarget = true
			break

		}
	}
	isShockActive := config.Simulation.DemandShock.Enabled &&
		step >= config.Simulation.DemandShock.StartStep &&
		step < config.Simulation.DemandShock.EndStep

	shockMultiplier := 1.0
	if isShockTarget && isShockActive {
		shockMultiplier = config.Simulation.DemandShock.Multiplier
	}

	localDemand := s.GenerateLocalDemand(step, config, shockMultiplier)
	forwardDemand := s.GenerateForwardDemandWithInboundShock(step, config, shockMultiplier, isShockActive)
	return append(localDemand, forwardDemand...)
}

func (s *Shard) GenerateLocalDemand(step int, config *Config, shockMultiplier float64) []*Load {
	basedemand := config.Demand.BaseDemandMatrix[s.Spec.ID][s.Spec.ID] * shockMultiplier
	price := s.Fee[len(s.Fee)-1]

	amount := basedemand * math.Pow(price, -config.Demand.LambdaMatrix[s.Spec.ID][s.Spec.ID])
	return []*Load{
		{
			ShardFrom:     s.Spec.ID,
			ShardTo:       s.Spec.ID,
			Amount:        amount,
			Step:          step,
			DelayedStep:   0,
			EffectiveStep: step,

			Forward: false,
		},
	}
}

func (s *Shard) GenerateForwardDemandWithInboundShock(step int, config *Config, shockMultiplier float64, isShockActive bool) []*Load {
	loads := make([]*Load, 0)
	for _, shard := range config.Shards {
		if shard.ID == s.Spec.ID {
			continue
		}

		baseMultiplier := shockMultiplier

		basedemand := config.Demand.BaseDemandMatrix[s.Spec.ID][shard.ID] * baseMultiplier
		sourcePrice := s.Fee[len(s.Fee)-1]
		targetPrice := s.Simulation.Shards[shard.ID].Fee[len(s.Simulation.Shards[shard.ID].Fee)-1]
		totalAmount := basedemand * math.Pow(sourcePrice, -config.Demand.LambdaMatrix[s.Spec.ID][shard.ID]) *
			math.Pow(targetPrice, -config.Demand.EpsilonMatrix[s.Spec.ID][shard.ID])

		if totalAmount > 0 {

			for delayStep := 1; delayStep <= config.Delay.MaxDelay; delayStep++ {
				weight := config.Delay.Weights[delayStep-1]
				if weight > 0 {
					partialAmount := totalAmount * weight
					loads = append(loads, &Load{
						ShardFrom:     s.Spec.ID,
						ShardTo:       shard.ID,
						Amount:        partialAmount,
						Step:          step,
						DelayedStep:   delayStep,
						EffectiveStep: step,
						Forward:       true,
					})
				}
			}
		}
	}
	return loads
}

func isShockTargetShard(shardID int, targetShards []int) bool {
	for _, targetShardID := range targetShards {
		if targetShardID == shardID {
			return true
		}
	}
	return false
}
