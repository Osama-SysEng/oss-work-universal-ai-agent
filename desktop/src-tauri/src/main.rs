// ═══════════════════════════════════════════════════════════════════
// OSS Work / OS_V1 — desktop shell
// Built by Osama Mohamed Fathy
// ═══════════════════════════════════════════════════════════════════
//
// This is a thin shell. It does not contain a model and it does not fake
// results: the window loads the live console that the Python runtime serves
// on the loopback interface, and the commands below call that same API.
//
// Prerequisites (Rust is not installed on the development machine):
//   - Rust: https://rustup.rs
//   - Tauri CLI: cargo install tauri-cli
//
// The runtime must be running first:
//   python -m osv1.interface.api
//
// Build:
//   cd desktop/src-tauri && cargo tauri build
// ═══════════════════════════════════════════════════════════════════

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;

const API: &str = "http://127.0.0.1:8080";

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_debugout::init())
        .invoke_handler(tauri::generate_handler![
            get_version,
            get_status,
            execute_task,
        ])
        .run(tauri::generate_context!())
        .expect("error while running the OS_V1 desktop shell");
}

// ── Tauri commands ────────────────────────────────────────────

#[tauri::command]
fn get_version() -> String {
    "1.0.0".to_string()
}

/// Ask the running runtime for its real status.
#[tauri::command]
async fn get_status() -> Result<Value, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{API}/status"))
        .send()
        .await
        .map_err(|error| format!("the OS_V1 runtime is not reachable: {error}"))?;
    response
        .json()
        .await
        .map_err(|error| format!("the runtime sent an answer we could not read: {error}"))
}

/// Run a task through the real pipeline: plan, decide, verify, and act.
#[tauri::command]
async fn execute_task(task: String) -> Result<Value, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{API}/build"))
        .json(&serde_json::json!({ "task": task, "agent_id": "" }))
        .send()
        .await
        .map_err(|error| format!("the OS_V1 runtime is not reachable: {error}"))?;
    response
        .json()
        .await
        .map_err(|error| format!("the runtime sent an answer we could not read: {error}"))
}
