package main
import "encoding/json"
type Cell struct { Value int64; Payload []int64 }
type State struct { Batches int; Width int; Retain int }
func prepare(raw string) *State { var s State; if err := json.Unmarshal([]byte(raw), &s); err != nil { panic(err) }; return &s }
func run(s *State) string {
    retained := [][]*Cell{}
    var checksum int64
    for batch := 0; batch < s.Batches; batch++ {
        cells := []*Cell{}
        for i := 0; i < s.Width; i++ {
            cell := &Cell{int64(batch+i), []int64{int64(i),int64(i+1),int64(i+2),int64(i+3)}}
            alias := cell; alias.Value++; alias.Payload[0]++
            cells = append(cells,cell)
        }
        for _, cell := range cells { checksum += cell.Value + cell.Payload[0] }
        if s.Retain > 0 {
            if len(retained) < s.Retain { retained = append(retained,cells)
            } else { retained[batch%s.Retain] = cells }
        }
    }
    var live int64
    for _, cells := range retained { for _, cell := range cells { live += cell.Value + cell.Payload[0] } }
    out, _ := json.Marshal([]int64{checksum,live}); return string(out)
}
