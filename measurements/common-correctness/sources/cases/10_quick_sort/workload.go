package main

import "encoding/json"

type State struct{ Values []int64 }

func prepare(raw string) *State {
	var s State
	if err := json.Unmarshal([]byte(raw), &s); err != nil {
		panic(err)
	}
	return &s
}
func run(s *State) string {
	a := []int64{}
	for _, v := range s.Values {
		a = append(a, v)
	}
	lows, highs, top := []int{0}, []int{len(a) - 1}, 1
	for top > 0 {
		top--
		lo, hi := lows[top], highs[top]
		if lo >= hi {
			continue
		}
		pivot := a[lo+(hi-lo)/2]
		lt, i, gt := lo, lo, hi
		for i <= gt {
			if a[i] < pivot {
				a[lt], a[i] = a[i], a[lt]
				lt++
				i++
			} else if a[i] > pivot {
				a[gt], a[i] = a[i], a[gt]
				gt--
			} else {
				i++
			}
		}
		if top == len(lows) {
			lows = append(lows, lo)
			highs = append(highs, lt-1)
		} else {
			lows[top] = lo
			highs[top] = lt - 1
		}
		top++
		if top == len(lows) {
			lows = append(lows, gt+1)
			highs = append(highs, hi)
		} else {
			lows[top] = gt + 1
			highs[top] = hi
		}
		top++
	}
	b, e := json.Marshal(a)
	if e != nil {
		panic(e)
	}
	return string(b)
}
