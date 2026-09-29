package main
import "encoding/json"
type State struct { Values []int64 }
func prepare(raw string) *State {
    var s State
    if err := json.Unmarshal([]byte(raw), &s); err != nil { panic(err) }
    return &s
}
func run(s *State) string {
    a, b := []int64{}, []int64{}
    for _, value := range s.Values { a = append(a, value); b = append(b, 0) }
    n := len(a)
    for width := 1; width < n; width *= 2 {
        for lo := 0; lo < n; lo += 2*width {
            mid, hi := min(lo+width,n), min(lo+2*width,n)
            i,j := lo,mid
            for k := lo; k < hi; k++ {
                if i < mid && (j >= hi || a[i] <= a[j]) { b[k] = a[i]; i++
                } else { b[k] = a[j]; j++ }
            }
        }
        a,b = b,a
    }
    out, err := json.Marshal(a)
    if err != nil { panic(err) }
    return string(out)
}
