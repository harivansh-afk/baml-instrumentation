use std::io::{self, BufRead, Write};
use axum::{Router, routing::{get,post}, http::StatusCode, extract::DefaultBodyLimit};
mod aggregate;
async fn handle(body: String) -> (StatusCode, [(&'static str, &'static str); 2], String) {
    let result = aggregate::aggregate(&body);
    let status = if result == r#"{"error":"invalid"}"# { StatusCode::BAD_REQUEST } else { StatusCode::OK };
    (status, [("content-type", "application/json"), ("connection", "close")], result)
}
#[tokio::main(flavor="current_thread")]
async fn main() {
    let mut addr = String::new(); io::stdin().read_line(&mut addr).unwrap();
    let listener = tokio::net::TcpListener::bind(addr.trim()).await.unwrap();
    let app = Router::new().route("/hello",get(|| async { ([("content-type", "application/json"), ("connection", "close")], r#"{"message":"Hello, world!"}"#) })).route("/aggregate",post(handle)).layer(DefaultBodyLimit::max(64*1024*1024));
    println!("@ready"); io::stdout().flush().unwrap();
    axum::serve(listener,app).with_graceful_shutdown(async {
        tokio::task::spawn_blocking(|| { let _ = io::stdin().lock().lines().next(); }).await.unwrap();
    }).await.unwrap();
}
