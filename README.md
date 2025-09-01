# Insurance-AI-Assistant
## 🛡️ Insurance AI Assistant

The Insurance AI Assistant is an intelligent system designed to assist insurance companies in **policy verification, fraud detection, and customer query handling** using Retrieval-Augmented Generation (RAG) and LLMs.  

It can automatically process policy documents, detect fraud, answer user queries, and escalate doubtful cases to human teams while maintaining full audit logs.

<details>
<summary>📂 Project Structure</summary>

```bash
.
├── backend-api/
├── embedding-service/
├── rag-service/
├── ingestion-service/
├── frontend/
├── embedding-server/
├── docker-compose.yml
├── models.sql
├── README.md
```
- backend-api/ – FastAPI backend (auth, orchestration, email handling)
- embedding-service/ – Embedding generator for semantic search
- rag-service/ – Retrieval-Augmented Generation pipeline
- ingestion-service/ – Policy ingestion & extraction
- frontend/ – Customer & backend team UI
- embedding-server/ – Vector server for embeddings
- docker-compose.yml – Multi-service orchestration
- models.sql – Postgres DB initialisation
- README.md – Documentation

</details> 

## 🚀 Features

- 📄 **Policy Document Ingestion** – Extract structured policy details from uploaded documents  
- 🔍 **Policy Verification** – Check extracted details against the policy database  
- ⚠️ **Fraud Detection** – If mismatched, automatically send a fraud alert email to the Fraud Prevention team  
- 💬 **AI-powered Q&A** – Answer customer queries about coverage, claims, surgeries, etc.  
- 🤔 **Confidence-based Escalation**  
  - High confidence → Direct AI answers to the user  
  - Low confidence → Summarised query forwarded to backend human team  
- 📝 **Conversation Summarisation** – Every interaction is summarised and logged for review  
- ✅ **Hallucination Check** – Lightweight verification model ensures answers are grounded in retrieved documents  

## Design Diagram
<img width="19664" height="6381" alt="system_architecture_fraudflow" src="https://github.com/user-attachments/assets/38ee246b-3a30-4b2f-b70a-fbab2863efd1" />

## 📖 Workflow

1. Upload Policy Document → Ingest & extract details.
2. Verification → Compare against DB.
  - ✅ Match → Continue normal processing.
  - ❌ Mismatch → Fraud alert email sent.
3. Customer Q&A → AI answers based on retrieved documents.
4. Confidence Check →
  - High → AI responds directly.
  - Low → Summarised query sent to backend team.
5. Summarization → All conversations logged & reviewed.
6. Hallucination Check → Light model ensures answers are grounded.

## ✅ Roadmap
- **ML-based Fraud Anomaly Detection** – go beyond rule-based mismatches to detect suspicious patterns.
- **Multi-language Policy Support** – support ingestion and Q&A in multiple languages.
- **Cloud Deployment (GCP/Azure) with CI/CD** – production-ready cloud deployment with automated pipelines.
- **Data Privacy Enhancements** – mask sensitive customer/policy details when interacting with OpenAI or external LLMs.
- **Support for Multiple Policy Types** – Extend to health, auto, home, and other insurance policies.
- **Efficient Document Querying** – optimise embeddings, retrieval, and summarisation for faster responses.

## 🤝 Contributing

Fork the repo → create a feature branch → open a PR.

## 📜 License

Licensed under MIT License
.
