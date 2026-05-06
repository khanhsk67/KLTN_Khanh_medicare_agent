# Tài liệu tổng quan dự án Medical RAG

## 1. Mục tiêu dự án

`Medical RAG` là hệ thống tư vấn y tế dùng AI, kết hợp:

- `Angular 20 standalone` cho frontend
- `FastAPI` cho backend
- `PostgreSQL` để lưu người dùng, phiên chat, tin nhắn, phân tích sức khỏe và dữ liệu ví điểm
- `Qdrant` để lưu vector tài liệu y khoa phục vụ RAG
- `Google Gemini` để phân tích ảnh, suy luận trên tài liệu và sinh câu trả lời
- `LangGraph` để điều phối pipeline tư vấn y tế

Các năng lực chính hiện có trong code:

- Đăng ký, đăng nhập, refresh token, lấy profile
- Chat tư vấn y tế bằng văn bản hoặc kèm ảnh
- Truy xuất tài liệu y khoa liên quan từ Qdrant
- Streaming câu trả lời AI theo thời gian thực
- Lưu lịch sử chat và xem chi tiết từng phiên
- Dashboard sức khỏe và timeline sức khỏe
- Ví điểm, điểm danh hằng ngày, mã khuyến mãi
- Cảnh báo nguy cơ sức khỏe theo thời tiết Hà Nội

## 2. Kiến trúc tổng thể

### Frontend

Frontend nằm tại `frontend/src/app`, tổ chức theo 3 lớp:

- `core/`: service, guard, interceptor, model dùng chung
- `features/`: auth, chat, history, analysis, wallet
- `shared/`: layout, wallet widget, pipe dùng lại

Entrypoint frontend:

- `frontend/src/main.ts`
- `frontend/src/app/app.routes.ts`
- `frontend/src/app/app.config.ts`

### Backend

Backend nằm tại `backend/app`, chia thành:

- `api/routes/`: FastAPI endpoints
- `services/`: nghiệp vụ
- `agents/`: LangGraph pipeline và AI agents
- `db/`: session DB và ORM models
- `core/`: config, prompts, security, limiter
- `models/`: schema Pydantic
- `utils/`: helper

Entrypoint backend:

- `backend/main.py`

## 3. Luồng hoạt động chính của dự án

### 3.1. Luồng khởi động hệ thống

1. Backend khởi tạo tại `backend/main.py`
2. Trong `lifespan`, backend:
   - tạo Qdrant collection nếu chưa có
   - seed promo code mặc định
3. Backend mount các router:
   - `auth`
   - `chat`
   - `history`
   - `analysis`
   - `weather`
   - `wallet`
   - `checkin`
   - `promo`
4. Frontend bootstrap Angular tại `frontend/src/main.ts`
5. Frontend điều hướng theo `frontend/src/app/app.routes.ts`

### 3.2. Luồng đăng ký và đăng nhập

1. Người dùng vào:
   - `frontend/src/app/features/auth/register/register.component.ts`
   - `frontend/src/app/features/auth/login/login.component.ts`
2. Frontend gọi:
   - `AuthService.register()`
   - `AuthService.login()`
3. Backend nhận request qua:
   - `backend/app/api/routes/auth.py`
4. Nghiệp vụ xử lý tại:
   - `backend/app/services/auth_service.py`
5. Frontend lưu `access_token` và `refresh_token` vào `sessionStorage`
6. Route bảo vệ bằng:
   - `frontend/src/app/core/guards/auth.guard.ts`
7. Request HTTP gắn JWT qua: 
   - `frontend/src/app/core/interceptors/jwt.interceptor.ts`

### 3.3. Luồng chat tư vấn y tế

1. Người dùng nhập tin nhắn hoặc ảnh tại:
   - `frontend/src/app/features/chat/chat.component.ts`
   - `frontend/src/app/features/chat/components/chat-input.component.ts`
2. Frontend stream dữ liệu qua:
   - `frontend/src/app/core/services/chat.service.ts`
3. Backend nhận tại:
   - `POST /api/chat/stream`
   - `backend/app/api/routes/chat.py`
4. Route chat gọi `run_medical_graph()` tại:
   - `backend/app/agents/orchestrator.py`
5. Pipeline LangGraph chạy theo các bước:
   - `analyze_image`
   - `retrieve_rules`
   - `generate_response`
   - `persist_to_db`
6. Backend stream SSE về frontend theo event:
   - `start`
   - `token`
   - `done`
   - `error`
7. Frontend ghép token để hiển thị câu trả lời theo thời gian thực

### 3.4. Luồng xem lịch sử chat

1. Người dùng vào:
   - `frontend/src/app/features/history/history.component.ts`
2. Frontend gọi:
   - `ApiService.getHistory()`
   - `ApiService.deleteSession()`
3. Backend xử lý tại:
   - `backend/app/api/routes/history.py`
   - `backend/app/services/history_service.py`
4. Khi xem chi tiết một session, frontend gọi:
   - `GET /api/history/sessions/{session_id}`

### 3.5. Luồng phân tích sức khỏe

1. Người dùng vào:
   - `frontend/src/app/features/analysis/analysis.component.ts`
2. Frontend gọi song song:
   - `ApiService.getDashboard(days)`
   - `ApiService.getHealthTimeline(days)`
   - `ApiService.getWeatherRisk()`
3. Backend xử lý qua:
   - `backend/app/api/routes/analysis.py`
   - `backend/app/api/routes/weather.py`
4. Dữ liệu được tổng hợp chủ yếu từ:
   - `TreatmentRecord`
   - `ChatSession`
   - `ChatMessage`

### 3.6. Luồng ví điểm và phần thưởng

1. Người dùng xem ví tại:
   - `frontend/src/app/features/wallet/wallet.component.ts`
   - `frontend/src/app/shared/components/wallet-widget.component.ts`
2. Frontend gọi:
   - `GET /api/wallet`
   - `GET /api/wallet/topup-history`
   - `GET /api/checkin/status`
   - `POST /api/checkin/daily`
   - `POST /api/promo-codes/redeem`
3. Backend xử lý tại:
   - `backend/app/api/routes/wallet.py`
   - `backend/app/api/routes/checkin.py`
   - `backend/app/api/routes/promo.py`
4. Nghiệp vụ nằm tại:
   - `backend/app/services/wallet_service.py`
   - `backend/app/services/checkin_service.py`
   - `backend/app/services/promo_service.py`

## 4. Các chức năng đang có và file code liên quan

### 4.1. Xác thực người dùng

- Đăng ký:
  - FE: `frontend/src/app/features/auth/register/register.component.ts`
  - FE service: `frontend/src/app/core/services/auth.service.ts`
  - BE route: `backend/app/api/routes/auth.py`
  - BE service: `backend/app/services/auth_service.py`
- Đăng nhập:
  - FE: `frontend/src/app/features/auth/login/login.component.ts`
  - FE service: `frontend/src/app/core/services/auth.service.ts`
  - BE route: `backend/app/api/routes/auth.py`
  - BE service: `backend/app/services/auth_service.py`
- Refresh token:
  - FE: `frontend/src/app/core/interceptors/jwt.interceptor.ts`
  - FE service: `frontend/src/app/core/services/auth.service.ts`
  - BE: `backend/app/api/routes/auth.py`, `backend/app/services/auth_service.py`
- Lấy profile:
  - FE service: `frontend/src/app/core/services/auth.service.ts`
  - BE: `backend/app/api/routes/auth.py`

### 4.2. Chat với AI y tế

- FE chat screen:
  - `frontend/src/app/features/chat/chat.component.ts`
  - `frontend/src/app/features/chat/components/chat-input.component.ts`
  - `frontend/src/app/features/chat/components/chat-messages.component.ts`
  - `frontend/src/app/features/chat/components/emergency-banner.component.ts`
- FE stream service:
  - `frontend/src/app/core/services/chat.service.ts`
- BE route:
  - `backend/app/api/routes/chat.py`
- BE AI orchestration:
  - `backend/app/agents/orchestrator.py`
  - `backend/app/agents/image_medical_agent.py`
  - `backend/app/agents/rule_medical_agent.py`
  - `backend/app/agents/chatbot_agent.py`
- BE persistence:
  - `backend/app/services/chat_service.py`

### 4.3. Lịch sử hội thoại

- FE:
  - `frontend/src/app/features/history/history.component.ts`
  - `frontend/src/app/features/history/components/session-detail.component.ts`
- BE:
  - `backend/app/api/routes/history.py`
  - `backend/app/services/history_service.py`

### 4.4. Dashboard và phân tích sức khỏe

- FE:
  - `frontend/src/app/features/analysis/analysis.component.ts`
  - `frontend/src/app/features/analysis/analysis.component.html`
- BE:
  - `backend/app/api/routes/analysis.py`
  - `backend/app/services/analysis_service.py`

### 4.5. Ví điểm, check-in, promo

- FE ví:
  - `frontend/src/app/features/wallet/wallet.component.ts`
  - `frontend/src/app/shared/components/wallet-widget.component.ts`
- BE route:
  - `backend/app/api/routes/wallet.py`
  - `backend/app/api/routes/checkin.py`
  - `backend/app/api/routes/promo.py`
- BE service:
  - `backend/app/services/wallet_service.py`
  - `backend/app/services/checkin_service.py`
  - `backend/app/services/promo_service.py`

### 4.6. Weather risk

- FE:
  - `frontend/src/app/features/analysis/analysis.component.ts`
- BE:
  - `backend/app/api/routes/weather.py`
  - `backend/app/services/weather_service.py`

### 4.7. Health check hệ thống

- `backend/main.py`
- endpoint: `GET /api/health`

### 4.8. Nạp tài liệu y khoa vào vector DB

- Script ingest PDF:
  - `backend/scripts/ingest_pdf.py`
- Vector store:
  - `backend/app/services/vector_store.py`

## 5. Các module backend và công dụng

### 5.1. Module `api`

Đường dẫn: `backend/app/api`

Chức năng:

- nhận request từ frontend
- validate dữ liệu
- gọi service hoặc agent
- trả response

Các route chính hiện có:

- `auth.py`
- `chat.py`
- `history.py`
- `analysis.py`
- `wallet.py`
- `checkin.py`
- `promo.py`
- `weather.py`

### 5.2. Module `services`

Đường dẫn: `backend/app/services`

Chức năng:

- chứa nghiệp vụ chính của hệ thống
- là lớp trung gian giữa router, agent, database và vector DB

Các service đáng chú ý:

- `auth_service.py`
- `chat_service.py`
- `history_service.py`
- `analysis_service.py`
- `wallet_service.py`
- `checkin_service.py`
- `promo_service.py`
- `weather_service.py`
- `vector_store.py`
- `rag_service.py` hiện vẫn là placeholder, không phải luồng chính đang dùng

### 5.3. Module `agents`

Đường dẫn: `backend/app/agents`

Chức năng:

- chứa pipeline AI và các agent chuyên trách
- là lõi xử lý RAG của hệ thống

Các file chính:

- `orchestrator.py`
- `image_medical_agent.py`
- `rule_medical_agent.py`
- `chatbot_agent.py`
- `treatment_analysis_agent.py`
- `medical_agent.py` hiện là placeholder

### 5.4. Module `db`

Đường dẫn: `backend/app/db`

Chức năng:

- kết nối PostgreSQL
- định nghĩa ORM models
- quản lý transaction/session cho request

Các model chính:

- `user.py`
- `chat_session.py`
- `chat_message.py`
- `treatment_record.py`
- `wallet.py`
- `point_transaction.py`
- `daily_checkin.py`
- `promo_code.py`
- `chat_usage.py`

### 5.5. Module `core`

Đường dẫn: `backend/app/core`

Chức năng:

- cấu hình ứng dụng
- JWT và xác thực
- prompts cho AI
- rate limiting

### 5.6. Module `models`

Đường dẫn: `backend/app/models`

Chức năng:

- schema request/response giữa frontend và backend
- `AgentState` cho LangGraph

### 5.7. Module `utils`

Đường dẫn: `backend/app/utils`

Chức năng:

- helper dùng chung
- helper xử lý weather mapping

## 6. Dữ liệu chính của hệ thống

### Bảng `users`

- lưu tài khoản người dùng

### Bảng `chat_sessions`

- mỗi phiên tư vấn tương ứng một session
- gắn với một user

### Bảng `chat_messages`

- lưu từng tin nhắn user và assistant
- có thể lưu `sources` và `urgency_level`

### Bảng `treatment_records`

- lưu dữ liệu phân tích y tế rút ra sau một phiên chat

### Bảng `wallets`

- lưu số dư điểm của người dùng

### Bảng `point_transactions`

- lưu lịch sử cộng hoặc trừ điểm

### Bảng `daily_checkins`

- lưu trạng thái điểm danh hằng ngày

### Bảng `promo_codes`

- lưu mã khuyến mãi và trạng thái sử dụng

### Bảng `chat_usage`

- lưu thống kê tiêu thụ điểm hoặc usage liên quan đến chat

## 7. Các route chính của backend

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
- `POST /api/auth/logout`

### Chat

- `POST /api/chat/stream`
- `GET /api/chat/sessions/new`

### History

- `GET /api/history/sessions`
- `GET /api/history/sessions/{session_id}`
- `DELETE /api/history/sessions/{session_id}`
- `GET /api/history/search`

### Analysis

- `GET /api/analysis/summary`
- `GET /api/analysis/timeline`
- `GET /api/analysis/statistics`
- `GET /api/analysis/dashboard`
- `GET /api/analysis/health-timeline`

### Wallet / Reward

- `GET /api/wallet`
- `GET /api/wallet/topup-history`
- `GET /api/checkin/status`
- `POST /api/checkin/daily`
- `POST /api/promo-codes/redeem`
- `POST /api/promo-codes/admin/add-points`

### Weather

- `GET /api/health-risk/hanoi`
- `GET /api/health-risk/hanoi/public`

### System

- `GET /api/health`
- `GET /`

## 8. Ghi chú kỹ thuật đáng chú ý

- Frontend auth token hiện được lưu trong `sessionStorage`, không phải `localStorage`
- Luồng chat dùng `fetch + ReadableStream` để đọc SSE, không dùng `EventSource`
- Backend commit dữ liệu ngay trong bước `persist_to_db` để frontend có thể tải lại session sau khi stream xong
- `QdrantService` là phần RAG đang dùng thực tế; `rag_service.py` chưa phải luồng chính
- Trong frontend vẫn có một số method trong `ApiService` mang dấu vết cũ hoặc chưa khớp hoàn toàn với route backend hiện tại
- README cũ từng mô tả frontend như React; code thực tế hiện tại là Angular standalone

## 9. File nên đọc đầu tiên nếu muốn onboard nhanh

- `backend/main.py`
- `backend/app/agents/orchestrator.py`
- `backend/app/agents/rule_medical_agent.py`
- `backend/app/api/routes/chat.py`
- `backend/app/services/analysis_service.py`
- `backend/app/api/routes/wallet.py`
- `frontend/src/app/app.routes.ts`
- `frontend/src/app/features/chat/chat.component.ts`
- `frontend/src/app/core/services/chat.service.ts`
- `frontend/src/app/features/wallet/wallet.component.ts`
