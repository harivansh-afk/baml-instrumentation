package main
import ("bufio"; "context"; "fmt"; "io"; "net"; "net/http"; "os")
func main() {
    scanner := bufio.NewScanner(os.Stdin)
    if !scanner.Scan() { panic("address missing") }
    listener, err := net.Listen("tcp",scanner.Text()); if err != nil { panic(err) }
    mux := http.NewServeMux()
    mux.HandleFunc("GET /health",func(w http.ResponseWriter,r *http.Request) { fmt.Fprint(w,"42") })
    mux.HandleFunc("POST /aggregate",func(w http.ResponseWriter,r *http.Request) {
        raw, err := io.ReadAll(http.MaxBytesReader(w,r.Body,64*1024*1024)); if err != nil { http.Error(w,"too large",413); return }
        body := aggregate(string(raw))
        w.Header().Set("Content-Type","application/json"); w.Header().Set("Connection","close")
        if body == `{"error":"invalid"}` { w.WriteHeader(400) }
        fmt.Fprint(w,body)
    })
    server := &http.Server{Handler:mux}
    go func() { if err := server.Serve(listener); err != nil && err != http.ErrServerClosed { panic(err) } }()
    fmt.Println("@ready")
    scanner.Scan()
    if err := server.Shutdown(context.Background()); err != nil { panic(err) }
}
