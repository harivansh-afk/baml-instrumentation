package main

import (
    "bufio"
    "fmt"
    "os"
    "strconv"
)

func main() {
    scanner := bufio.NewScanner(os.Stdin)
    scanner.Buffer(make([]byte, 65536), 64*1024*1024)
    line := func() string {
        if !scanner.Scan() { panic("unexpected EOF") }
        return scanner.Text()
    }
    state := prepare(line())
    fmt.Println("@ready")
    for {
        count, err := strconv.Atoi(line())
        if err != nil { panic(err) }
        if count == 0 { return }
        for i := 0; i < count; i++ { fmt.Println("@result " + run(state)) }
        fmt.Println("@done")
    }
}
