package main

import (
	"fmt"
	"gas-for-multiple-shards/core"
	"log"
	"sort"
)

func main() {

	config, err := core.LoadConfig("config.yml")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	fmt.Printf("Enhanced Gas Fee Simulation - %d shards, %d steps\n",
		config.Network.NumShards, config.Simulation.TotalSteps)

	simulation := core.NewSimulation(*config)

	logger := core.NewSimulationLogger(simulation)
	logger.RunAndLog()

	fmt.Println("Per-step log written to enhanced_simulation_analysis_<timestamp>.log")

	fmt.Println("\nFinal Results:")

	shardIDs := make([]int, 0, len(simulation.Shards))
	for shardID := range simulation.Shards {
		shardIDs = append(shardIDs, shardID)
	}
	sort.Ints(shardIDs)

	for _, shardID := range shardIDs {
		shard := simulation.Shards[shardID]
		finalFee := shard.Fee[len(shard.Fee)-1]
		fmt.Printf("Shard %d: Fee = %.6f\n", shardID, finalFee)
	}
}
