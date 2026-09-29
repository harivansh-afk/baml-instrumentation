package main

import (
	"encoding/json"
	"strconv"
)

type State struct {
	Count int
	Seed  int64
}

func prepare(raw string) *State {
	var s State
	if err := json.Unmarshal([]byte(raw), &s); err != nil {
		panic(err)
	}
	return &s
}
func leaf(value int64) int64 { return value + 1 }
func run(s *State) string {
	value := s.Seed
	for i := 0; i < s.Count; i++ {
		value = leaf(value)
	}
	return strconv.FormatInt(value, 10)
}
