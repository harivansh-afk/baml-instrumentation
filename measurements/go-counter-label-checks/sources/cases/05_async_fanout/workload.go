package main
import ("encoding/json"; "time")
type State struct { Fanout int; DelayMs int `json:"delay_ms"`; PayloadSize int `json:"payload_size"` }
func prepare(raw string) *State { var s State; if err := json.Unmarshal([]byte(raw), &s); err != nil { panic(err) }; return &s }
func run(s *State) string {
    tasks := []chan int64{}
    for i := 0; i < s.Fanout; i++ {
        ch := make(chan int64,1); tasks = append(tasks,ch)
        go func(i int, ch chan int64) {
            payload := []int64{}
            for j := 0; j < s.PayloadSize; j++ { payload = append(payload,int64(i+j)) }
            time.Sleep(time.Duration(s.DelayMs)*time.Millisecond)
            var sum int64
            for _, v := range payload { sum += v }
            ch <- sum
        }(i,ch)
    }
    results := []int64{}
    for _, task := range tasks { results = append(results,<-task) }
    out, _ := json.Marshal(results); return string(out)
}
