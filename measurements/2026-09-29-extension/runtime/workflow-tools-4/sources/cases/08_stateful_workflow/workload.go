package main

import (
	"encoding/json"
	"sort"
	"time"
)

type Config struct {
	Requests              []string
	Batch, Retain, Fanout int
	DelayMs               int `json:"delay_ms"`
	Capture               bool
}
type Item struct {
	Kind    string
	Amount  *int64
	Payload *[]int64
}
type Request struct {
	Key, Mode string
	Items     *[]Item
}
type Cell struct {
	Id      int
	Value   int64
	Payload []int64
}
type Entry struct {
	Total int64
	Cells []Cell
}
type State struct {
	Config                Config
	Cache                 map[string]Entry
	Order                 []string
	Slot, Cursor          int
	Digest, ResponseBytes int64
}
type Response struct {
	Seq     int    `json:"seq"`
	Ok      bool   `json:"ok"`
	Key     string `json:"key"`
	Total   int64  `json:"total"`
	Check   int64  `json:"check"`
	Evicted string `json:"evicted"`
}
type Snapshot struct {
	Key   string `json:"key"`
	Total int64  `json:"total"`
	Check int64  `json:"check"`
	Count int    `json:"count"`
}
type Result struct {
	Processed     int        `json:"processed"`
	Digest        int64      `json:"digest"`
	ResponseBytes int64      `json:"response_bytes"`
	Cache         []Snapshot `json:"cache"`
	Responses     []Response `json:"responses"`
}

func prepare(raw string) *State {
	s := &State{Cache: map[string]Entry{}, Order: []string{}}
	if err := json.Unmarshal([]byte(raw), &s.Config); err != nil {
		panic(err)
	}
	return s
}
func tool(req *Request, worker, delay int) []Cell {
	cells := []Cell{}
	for i := worker; i < len(*req.Items); i += 4 {
		item := (*req.Items)[i]
		var value int64
		if item.Kind == "credit" {
			value = *item.Amount
		} else if item.Kind == "debit" {
			value = -*item.Amount
		}
		payload := []int64{}
		for _, v := range *item.Payload {
			payload = append(payload, v+int64(worker)+1)
		}
		cells = append(cells, Cell{i, value, payload})
	}
	if delay > 0 {
		time.Sleep(time.Duration(delay) * time.Millisecond)
	}
	return cells
}
func cellSum(c Cell) int64 {
	v := c.Value
	for _, x := range c.Payload {
		v += x
	}
	return v
}
func liveCheck(cells []Cell) int64 {
	var v int64
	for _, c := range cells {
		v += int64(c.Id+1) * cellSum(c)
	}
	return v
}
func process(s *State, raw string) Response {
	invalid := Response{Seq: s.Cursor}
	var req Request
	if json.Unmarshal([]byte(raw), &req) != nil || req.Key == "" || (req.Mode != "replace" && req.Mode != "accumulate") || req.Items == nil {
		return invalid
	}
	for _, b := range []byte(req.Key) {
		if b > 127 {
			return invalid
		}
	}
	for _, item := range *req.Items {
		if (item.Kind != "credit" && item.Kind != "debit" && item.Kind != "skip") || item.Amount == nil || *item.Amount < 0 || *item.Amount > 1000000 || item.Payload == nil {
			return invalid
		}
		for _, v := range *item.Payload {
			if v < 0 || v > 1000000 {
				return invalid
			}
		}
	}
	parts := [][]Cell{}
	if s.Config.Fanout == 4 {
		channels := []chan []Cell{}
		for i := 0; i < 4; i++ {
			ch := make(chan []Cell, 1)
			channels = append(channels, ch)
			go func(worker int) { ch <- tool(&req, worker, s.Config.DelayMs) }(i)
		}
		for _, ch := range channels {
			parts = append(parts, <-ch)
		}
	} else {
		for i := 0; i < 4; i++ {
			parts = append(parts, tool(&req, i, s.Config.DelayMs))
		}
	}
	cells := []Cell{}
	var total int64
	for _, part := range parts {
		for _, c := range part {
			cells = append(cells, c)
			total += cellSum(c)
		}
	}
	previous, exists := s.Cache[req.Key]
	if req.Mode == "accumulate" {
		total += previous.Total
	}
	evicted := ""
	if s.Config.Retain > 0 {
		if !exists {
			if len(s.Order) < s.Config.Retain {
				s.Order = append(s.Order, req.Key)
			} else {
				evicted = s.Order[s.Slot]
				delete(s.Cache, evicted)
				s.Order[s.Slot] = req.Key
				s.Slot = (s.Slot + 1) % s.Config.Retain
			}
		}
		s.Cache[req.Key] = Entry{total, cells}
	}
	return Response{s.Cursor, true, req.Key, total, liveCheck(cells), evicted}
}
func run(s *State) string {
	responses := []Response{}
	for i := 0; i < s.Config.Batch; i++ {
		response := process(s, s.Config.Requests[s.Cursor%len(s.Config.Requests)])
		encoded, err := json.Marshal(response)
		if err != nil {
			panic(err)
		}
		s.ResponseBytes += int64(len(encoded))
		var ok int64
		if response.Ok {
			ok = 1
		}
		for _, v := range []int64{int64(s.Cursor), ok, response.Total, response.Check, int64(len(s.Cache))} {
			s.Digest = ((s.Digest*257+v)%1000000007 + 1000000007) % 1000000007
		}
		if s.Config.Capture {
			responses = append(responses, response)
		}
		s.Cursor++
	}
	keys := []string{}
	for key := range s.Cache {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	snapshot := []Snapshot{}
	for _, key := range keys {
		e := s.Cache[key]
		snapshot = append(snapshot, Snapshot{key, e.Total, liveCheck(e.Cells), len(e.Cells)})
	}
	encoded, err := json.Marshal(Result{s.Cursor, s.Digest, s.ResponseBytes, snapshot, responses})
	if err != nil {
		panic(err)
	}
	return string(encoded)
}
