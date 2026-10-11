# PeCal Pulse

A voice-enabled AI sales assistant. **First place at Perschmann Calibration’s Hack The Lab.**

Our four-person team built a workspace to help Inside Sales identify opportunities for proactive customer outreach alongside their everyday quotation work.

## The workspace

- **Dashboard:** opportunity groups, filters and a prioritized customer view.
- **Customers:** activity history, forecasts, conversation preparation and follow-ups.
- **Insights:** sector trends, comparisons and model-quality information.
- **Pulse:** an English/German voice assistant that understands the current page, operates controls, creates charts in chat, assigns work and prepares email drafts for review. It does not send emails automatically.

## Modelling

We used K-means for behavioral segmentation and opportunity grouping; logistic regression for activity prediction; and validation against tree-based models and simple volume baselines. Cadence-aware inactivity signals, peer comparisons and sector time-series analysis support outreach decisions.

Evaluation uses chronological splits rather than random time mixing. Activity predictions describe observed future activity, not confirmed churn or sales conversion. Forecast quantities and opportunity scores do not establish revenue, profit or the benefit of outreach.

## Technology

**Next.js / TypeScript**, assistant-ui, ECharts, Zustand and Motion on the frontend. **Python / FastAPI**, scikit-learn, NumPy, LangChain / LangGraph, OpenRouter and SQLite on the backend. **LiveKit**, Deepgram and Cartesia support streaming voice.

The assistant uses typed tools and current page context to navigate, change filters and open customer views. Generated charts remain in the conversation. Workflow updates and reviewed email drafts are stored separately from source data.

## Public repository

This repository retains implementation code and application contracts. Data directories, mock datasets, data examples, dataset-generating fixtures, data-bearing tests and screenshots are excluded at Perschmann’s request. Required local inputs are not distributed; this is not a runnable demo package.

The development sequence and six branches are preserved. Published history has been rewritten to remove excluded material; commit hashes have changed.

## Development credits

Built with AI-assisted development using **OpenAI Codex — GPT-6.1 Sol, medium reasoning**, and **Muse Spark 1.3, high reasoning**.
