package main
import ("encoding/json"; "math"; "sort"; "unicode/utf8")
type State struct { Raw string }
func prepare(raw string) *State { return &State{Raw:raw} }
func aggregate(raw string) string {
    const invalid = `{"error":"invalid"}`
    var value any
    if json.Unmarshal([]byte(raw), &value) != nil { return invalid }
    rows, ok := value.([]any)
    if !ok || len(rows) > 1000000 { return invalid }
    totals := map[string]int64{}
    for _, value := range rows {
        row, ok := value.(map[string]any); if !ok { return invalid }
        account, a := row["account"].(string)
        amount, b := row["amount_cents"].(float64)
        active, c := row["active"].(bool)
        if !a || !b || !c || !utf8.ValidString(account) { return invalid }
        for _, ch := range account { if ch > 127 { return invalid } }
        if math.IsNaN(amount) || math.IsInf(amount,0) || amount != math.Trunc(amount) || amount < 0 || amount > 1000000 { return invalid }
        if active { totals[account] += int64(amount) }
    }
    keys := []string{}
    for k := range totals { keys = append(keys,k) }
    sort.Strings(keys)
    type Total struct { Account string `json:"account"`; Total int64 `json:"total_cents"` }
    out := []Total{}
    for _, k := range keys { out = append(out,Total{k,totals[k]}) }
    encoded, err := json.Marshal(out); if err != nil { panic(err) }
    return string(encoded)
}
func run(s *State) string { return aggregate(s.Raw) }
