package main
import ("encoding/json"; "strconv")
type State struct { Values []int64; Variant string }
func prepare(raw string) *State {
    var s State
    if err := json.Unmarshal([]byte(raw), &s); err != nil { panic(err) }
    return &s
}
func run(s *State) string {
    values := s.Values
    if s.Variant == "build" {
        values = []int64{}
        for i := 0; i < len(s.Values); i++ { values = append(values, s.Values[i]) }
    }
    var total int64
    if s.Variant == "indexed" {
        for i := 0; i < len(values); i++ { total += values[i] }
    } else {
        for _, value := range values { total += value }
    }
    return strconv.FormatInt(total, 10)
}
