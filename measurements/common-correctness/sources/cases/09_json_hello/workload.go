package main

import "encoding/json"

type State struct {
	Message string `json:"message"`
}

func prepare(raw string) *State {
	var s State
	if err := json.Unmarshal([]byte(raw), &s); err != nil {
		panic(err)
	}
	return &s
}
func run(s *State) string {
	b, err := json.Marshal(s)
	if err != nil {
		panic(err)
	}
	return string(b)
}
