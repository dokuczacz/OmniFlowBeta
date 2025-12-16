# Omni Knowledge Base – Full Category Specification (v1.0)

This file defines all structured knowledge categories used in the Omni GPT system.
Each category contains deeply cleaned, deduplicated, and contextually meaningful entries ready for use in GPT-based systems or light ML tasks.

---

Purpose:
Ten dokument nie definiuje zachowania agenta ani funkcji sandboxa.
Określa jedynie semantyczne znaczenie kategorii pamięci używanych przez system Omni.
Wszystkie operacje na pamięci wykonuje system pamięci Omni zgodnie z zasadami opisanymi w PDF.


---


## 📂 Structure Overview


## 🧩 PE – Prompt Engineering  
Scaffolds GPT behavior using structured prompts, system commands (`SYS:`), memory blocks (`MEM:`), and logic flows (`TASK:`).  
**Common Tags:** `[SYS]`, `[TASK]`, `completion`, `instruction`, `JSON`, `generate`.

---

## 🧑‍💻 UI – User Interaction  
Captures input/output flows between user and assistant. Also includes UX feedback, corrections, and response traces.  
**Common Contexts:** `user clicked`, `input logged`, `feedback received`.

---

## 🧠 ML – Memory & Logs  
Stores memory structure, timestamped events, GPT recall chains, and self-awareness pings.  
**Used For:** planning memory, state syncing, long-term context tracking.

---

## 🧬 LO – Life Optimizer  
Personal assistant planning logic for wellness, balance, energy systems, assistant-powered routines.  
**Scope:** scheduling, work/rest planning, minimalist focus systems.

---

## 🧭 PS – Planning Strategy  
Roadmap structure, long-term objectives, OKRs, sprint phases, goal trees.  
**Trigger Examples:** `plan`, `next milestone`, `feature breakdown`.

---

## 🛠 TM – Task Management  
Checklists, retry sequences, workflow automation, dev-ops routines.  
**Core Tags:** `task`, `todo`, `check`, `retry`, `exec`.

---

## 🧱 SYS – System Design  
Everything infrastructure: Azure, runtime, API calls, blob syncs, assistant handshakes.  
**Example Traces:** `azure config`, `blob connect`, `container ready`, `status 200`.

---

## ❓ GEN – General / Unclassified  
Used for valuable but ambiguous or meta entries not strongly fitting one category.  
Often includes assistant setup logic, inter-category transitions, or early raw logs.  
**Note:** GEN entries are retained only if meaningful.

---

## 🛠 ID Assignment Logic  
- Entry IDs are assigned sequentially **within each category**
  - Repeated categories in a row: assigned incrementally (e.g., PE.1, PE.2, PE.3)
  - Isolated category calls fill from any available empty number
  - This ensures full ID coverage without large gaps or jumps

---

## 📌 How to Use

- Each file contains multiple blocks of knowledge prefixed with:
  - A category tag: `🟢 CATEGORY – <Category Name>`  
  - A unique ID tag: [🕒(⚠️) <Category Name>.next order number.timestamp YYMMDDHHMM]

- The structure is optimized for:
  - GPT chat usage (retrieval-based context feeding)
  - Knowledge review
  - Data prep for prompt classification or training sets
