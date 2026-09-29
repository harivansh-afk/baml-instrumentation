package main
import ("encoding/json"; "strconv")
type State struct { Value int64 }
func prepare(raw string) *State {
	var s State
    if err := json.Unmarshal([]byte(raw), &s); err != nil { panic(err) }
    return &s
}
func run(s *State) string { return strconv.FormatInt(s.Value, 10) }
