package main

import (
	"encoding/json"
	"slices"
)

type State struct {
	Count int
	Seed  int64
}

func prepare(raw string) *State {
	var s State
	if e := json.Unmarshal([]byte(raw), &s); e != nil {
		panic(e)
	}
	return &s
}
func run(s *State) string {
	a := []int64{}
	v := s.Seed
	for i := 0; i < s.Count; i++ {
		v = v * 48271 % 1000000007
		a = append(a, v)
	}
	slices.Sort(a)
	b, e := json.Marshal(a)
	if e != nil {
		panic(e)
	}
	return string(b)
}
