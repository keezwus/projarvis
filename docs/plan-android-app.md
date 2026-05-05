# Android App (Jetpack Compose)

## Overview

Thin native client for projarvis. All logic lives server-side; the app is a chat UI that calls HTTP endpoints and displays results.

## Architecture

```
Activity → NavHost → Screens
                        ↓
                  ViewModel → projarvis API (HTTP Basic Auth)
```

Dependencies: Retrofit + OkHttp + Kotlinx Serialization + Navigation Compose + DataStore.

## API Surface

The app talks to these endpoints (all behind Caddy HTTPS + Basic Auth):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/agent/message` | Send user text, returns `{session_id, status, tools_to_approve, response_text}` |
| `POST` | `/api/v1/agent/approve` | Approve or reject pending tools |
| `DELETE` | `/api/v1/agent/session/{session_id}` | Clear session |
| `POST` | `/api/v1/commit` | Commit what-if plan → CalDAV sync |

## Interaction Flow

```
1. User types text → POST /agent/message
   ↓
2. Response:
   status = "completed"     → show response_text, done
   status = "awaiting_tools" → show tool cards + approve/reject button
   ↓
3. User taps approve / reject → POST /agent/approve {session_id, approved}
   ↓
4. Loop back to step 2 until completed
   ↓
5. User reviews proposed plan → taps "Commit" → POST /commit
```

## Screens

### 1. LoginScreen
- Username + password text fields
- "Connect" button → stores credentials in EncryptedSharedPreferences
- Navigate to ChatScreen on success (verify by calling GET /api/v1/plan)

### 2. ChatScreen
- LazyColumn of messages (user bubbles, assistant bubbles, tool cards)
- Bottom: TextField + send button
- Tool card: shows tool name + input, Approve / Reject buttons (only when status = awaiting_tools)
- Top bar: menu with "New Session" (clear_session + clear session_id) and "Logout"

### 3. CommitSheet (bottom sheet)
- Triggered by user tapping "Commit" after reviewing what-if results
- Shows success/error status

## Data Layer

```kotlin
// OkHttp client with Basic Auth interceptor
val client = OkHttpClient.Builder()
    .addInterceptor { chain ->
        val credential = Credentials.basic(username, password)
        chain.proceed(chain.request().newBuilder()
            .header("Authorization", credential)
            .build())
    }
    .build()

// Retrofit service
interface ProjarvisApi {
    @POST("/api/v1/agent/message")
    suspend fun sendMessage(@Body body: AgentMessageRequest): AgentResponse

    @POST("/api/v1/agent/approve")
    suspend fun approve(@Body body: AgentApproveRequest): AgentResponse

    @DELETE("/api/v1/agent/session/{session_id}")
    suspend fun clearSession(@Path("session_id") sessionId: String)

    @POST("/api/v1/commit")
    suspend fun commit(): CommitResponse
}
```

## State

- `baseUrl` — stored in DataStore (user enters `https://<domain>`)
- `username` / `password` — stored in EncryptedSharedPreferences
- `sessionId` — kept in ChatViewModel (lost on app kill; re-sending starts a new session)

## Build the App

1. Create new Android project with Empty Compose Activity
2. Add dependencies to `build.gradle.kts`
3. Copy `ProjarvisApi.kt`, models, screens
4. The app binary is independent — no changes needed to this repo.

## Decisions Not Taken

- Push notifications for "awaiting_tools" → use polling for now (POST /commit triggers sync)
- Offline mode → no local scheduling; server must be reachable
- Session persistence → service keeps sessions in memory; server restart loses them (future: SQLite)
