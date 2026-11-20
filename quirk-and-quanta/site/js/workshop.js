/**
 * Quirk & Quanta - Workshop Lab Controller
 * Drives the RAG exploration interface: questions, chunk strategy switching,
 * vector retrieval, BM25 lexical search, Hybrid RRF, comparison matrix, and telemetry.
 */

let goldenQuestions = [];
let isServerActive = false;

document.addEventListener('DOMContentLoaded', () => {
  initWorkshop();
});

async function initWorkshop() {
  setupControls();
  await checkBackendStatus();
  await loadGoldenQuestions();
}

function setupControls() {
  const topKSlider = document.getElementById('top-k-slider');
  const topKVal = document.getElementById('top-k-val');
  if (topKSlider && topKVal) {
    topKSlider.addEventListener('input', (e) => {
      topKVal.textContent = e.target.value;
    });
  }

  const presetSelect = document.getElementById('question-preset-select');
  const questionInput = document.getElementById('user-question-input');
  if (presetSelect && questionInput) {
    presetSelect.addEventListener('change', (e) => {
      const qid = e.target.value;
      if (!qid) return;
      const found = goldenQuestions.find(q => q.id === qid);
      if (found) {
        questionInput.value = found.question;
        // Auto set role if restricted
        const roleSelect = document.getElementById('role-select');
        if (roleSelect) {
          if (found.authorizedRoles && !found.authorizedRoles.includes('customer')) {
            roleSelect.value = 'admin';
          } else {
            roleSelect.value = 'customer';
          }
        }
      }
    });
  }

  const btnRetrieve = document.getElementById('btn-retrieve-only');
  if (btnRetrieve) {
    btnRetrieve.addEventListener('click', () => executeRAG(true));
  }

  const btnAsk = document.getElementById('btn-ask-rag');
  if (btnAsk) {
    btnAsk.addEventListener('click', () => executeRAG(false));
  }

  const btnCompare = document.getElementById('btn-compare-strategies');
  if (btnCompare) {
    btnCompare.addEventListener('click', () => executeCompare());
  }
}

async function checkBackendStatus() {
  const statusPill = document.getElementById('backend-status-pill');
  try {
    const res = await fetch('/api/rag/status');
    if (res.ok) {
      const data = await res.json();
      isServerActive = true;
      if (statusPill) {
        if (data.hasGeminiKey) {
          statusPill.textContent = '🟢 Live Gemini RAG Active';
          statusPill.className = 'badge badge-success';
        } else {
          statusPill.textContent = '🟡 Offline Reference Engine Active (BM25 + Hybrid Ready)';
          statusPill.className = 'badge badge-gold';
        }
      }
      return;
    }
  } catch (err) {
    isServerActive = false;
  }

  if (statusPill) {
    statusPill.textContent = '⚪ Static Reference Mode (Local)';
    statusPill.className = 'badge badge-navy';
    statusPill.title = "Run 'python3 quirk-and-quanta/rag/server.py' for live server endpoints";
  }
}

async function loadGoldenQuestions() {
  const selectEl = document.getElementById('question-preset-select');
  if (!selectEl) return;

  try {
    let res = await fetch('/api/rag/questions');
    if (!res.ok) {
      res = await fetch('../data/evaluation/golden_dataset.json');
    }
    if (res.ok) {
      goldenQuestions = await res.json();
      let html = '<option value="">-- Choose a test case (22 curated) --</option>';
      goldenQuestions.forEach(q => {
        const famLabel = q.family.replace(/_/g, ' ').toUpperCase();
        html += `<option value="${q.id}">[${famLabel}] ${q.question.slice(0, 65)}...</option>`;
      });
      selectEl.innerHTML = html;
    }
  } catch (e) {
    console.warn('Could not load golden questions:', e);
  }
}

async function executeRAG(retrievalOnly) {
  const questionInput = document.getElementById('user-question-input');
  const methodSelect = document.getElementById('method-select');
  const strategySelect = document.getElementById('strategy-select');
  const roleSelect = document.getElementById('role-select');
  const topKSlider = document.getElementById('top-k-slider');

  const question = questionInput ? questionInput.value.trim() : '';
  if (!question) {
    alert('Please enter a question or select a curated workshop query.');
    return;
  }

  const method = methodSelect ? methodSelect.value : 'vector';
  const strategy = strategySelect ? strategySelect.value : 'semantic';
  const role = roleSelect ? roleSelect.value : 'customer';
  const topK = topKSlider ? parseInt(topKSlider.value) : 5;

  const modeBadge = document.getElementById('execution-mode-badge');
  if (modeBadge) {
    modeBadge.textContent = `Running ${method.toUpperCase()} Search...`;
    modeBadge.className = 'badge badge-gold';
  }

  // Hide comparison wrapper if open
  const compWrapper = document.getElementById('comparison-card-wrapper');
  if (compWrapper) compWrapper.style.display = 'none';

  if (isServerActive) {
    const endpoint = retrievalOnly ? '/api/rag/retrieve' : '/api/rag/ask';
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: jsonPayload(question, topK, strategy, role, method)
      });
      if (res.ok) {
        const data = await res.json();
        renderResults(data, retrievalOnly);
        return;
      }
    } catch (err) {
      console.warn('Live API call failed, falling back to client reference handler:', err);
    }
  }

  // Fallback: Client-side reference handler
  executeClientFallback(question, topK, strategy, role, retrievalOnly);
}

async function executeCompare() {
  const questionInput = document.getElementById('user-question-input');
  const strategySelect = document.getElementById('strategy-select');
  const roleSelect = document.getElementById('role-select');
  const topKSlider = document.getElementById('top-k-slider');

  const question = questionInput ? questionInput.value.trim() : '';
  if (!question) {
    alert('Please enter a question to compare retrieval methods.');
    return;
  }

  const strategy = strategySelect ? strategySelect.value : 'semantic';
  const role = roleSelect ? roleSelect.value : 'customer';
  const topK = topKSlider ? parseInt(topKSlider.value) : 5;

  const compWrapper = document.getElementById('comparison-card-wrapper');
  const compGrid = document.getElementById('comparison-results-grid');

  if (!isServerActive) {
    alert('Server must be running (python3 quirk-and-quanta/rag/server.py 8000) for live comparison.');
    return;
  }

  try {
    const res = await fetch('/api/rag/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: question,
        topK: topK,
        strategy: strategy,
        role: role
      })
    });
    if (res.ok) {
      const data = await res.json();
      renderComparison(data);
      if (compWrapper) compWrapper.style.display = 'block';
    }
  } catch (err) {
    console.error('Error fetching comparison:', err);
  }
}

function renderComparison(data) {
  const compGrid = document.getElementById('comparison-results-grid');
  if (!compGrid) return;

  const strategies = [
    { title: '1. Dense Vector (Cosine)', key: 'vector', color: '#158D89' },
    { title: '2. Lexical BM25 (Inverted Index)', key: 'bm25', color: '#2B4C7E' },
    { title: '3. Hybrid (RRF Fusion k=60)', key: 'hybrid', color: '#B45309' }
  ];

  let html = '';
  strategies.forEach(st => {
    const res = data[st.key] || {};
    const evidence = res.evidence || [];
    html += `
      <div style="background: #FFFFFF; border: 1px solid var(--color-border); border-radius: 6px; padding: 12px;">
        <div style="font-weight: 800; font-size: 0.875rem; color: ${st.color}; margin-bottom: 8px; border-bottom: 2px solid ${st.color}; padding-bottom: 4px;">
          ${st.title}
        </div>
        <div style="font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 8px;">
          Latency: ${res.latency ? res.latency.totalMs : 0} ms &bull; ${evidence.length} results
        </div>
        <div style="display: flex; flex-direction: column; gap: 8px;">
    `;

    evidence.forEach((item, idx) => {
      const scoreLabel = st.key === 'hybrid' ? `RRF: ${item.score}` : (st.key === 'bm25' ? `BM25: ${item.score}` : `Cos: ${item.score}`);
      html += `
        <div style="font-size: 0.75rem; border: 1px solid var(--color-border); border-radius: 4px; padding: 6px; background: #FAFBFD;">
          <div style="display: flex; justify-content: space-between; font-weight: 700; color: var(--color-navy);">
            <span>#${idx + 1} ${escapeHtml(item.sourceId)}</span>
            <span style="color: ${st.color}; font-weight: 800;">${scoreLabel}</span>
          </div>
          <div style="color: var(--color-text-muted); font-size: 0.6875rem; margin-top: 2px;">
            ${escapeHtml(item.sectionTitle || 'Section')}
          </div>
        </div>
      `;
    });

    html += `
        </div>
      </div>
    `;
  });

  compGrid.innerHTML = html;
}

function jsonPayload(question, topK, strategy, role, method) {
  const hardenedCheck = document.getElementById('hardened-mode-checkbox');
  const isHardened = hardenedCheck ? hardenedCheck.checked : true;
  return JSON.stringify({
    question: question,
    topK: topK,
    strategy: strategy,
    role: role,
    method: method || 'auto',
    hardened: isHardened
  });
}

function renderResults(data, retrievalOnly) {
  const modeBadge = document.getElementById('execution-mode-badge');
  const timeEmb = document.getElementById('time-emb');
  const timeRet = document.getElementById('time-ret');
  const timeGen = document.getElementById('time-gen');
  const timeTotal = document.getElementById('time-total');
  const answerWrapper = document.getElementById('answer-card-wrapper');
  const answerText = document.getElementById('generated-answer-text');
  const citationsList = document.getElementById('answer-citations-list');
  const evidenceCount = document.getElementById('evidence-count-label');
  const evidenceList = document.getElementById('evidence-results-list');

  // Latency
  const lat = data.latency || {};
  if (timeEmb) timeEmb.textContent = `${lat.embeddingMs || 0} ms`;
  if (timeRet) timeRet.textContent = `${lat.retrievalMs || lat.vectorRetrievalMs || 0} ms`;
  if (timeGen) timeGen.textContent = `${lat.generationMs || 0} ms`;
  if (timeTotal) timeTotal.textContent = `${lat.totalMs || 0} ms`;

  // Mode Badge & Guardrail Alerts
  if (modeBadge) {
    if (data.guardrailAction === 'REJECT_INJECTION') {
      modeBadge.textContent = '🛡️ Prompt Injection Blocked';
      modeBadge.className = 'badge badge-danger';
    } else if (data.guardrailAction === 'REJECT_OFF_TOPIC') {
      modeBadge.textContent = '🔬 Scope Boundary Enforced (Coding Blocked)';
      modeBadge.className = 'badge badge-gold';
    } else if (data.guardrailAction === 'ABSTAIN_UNGROUNDED') {
      modeBadge.textContent = 'ℹ️ Grounded Abstention Triggered';
      modeBadge.className = 'badge badge-navy';
    } else if (data.guardrailAction === 'VULNERABLE_OVERRIDE_SIMULATED') {
      modeBadge.textContent = '🏴‍☠️ Vulnerable Persona Override (Demo)';
      modeBadge.className = 'badge badge-danger';
    } else {
      const isLive = data.executionMode === 'live_gemini';
      const methodTag = (data.retrievalMethod || 'vector').toUpperCase();
      modeBadge.textContent = isLive ? `Live Gemini (${methodTag})` : `Reference Synthesizer (${methodTag})`;
      modeBadge.className = isLive ? 'badge badge-success' : 'badge badge-navy';
    }
  }

  // Graph Path Visualization
  const graphWrapper = document.getElementById('graph-path-wrapper');
  const graphContainer = document.getElementById('graph-path-container');
  if (data.graphAnalysis && graphWrapper && graphContainer) {
    graphWrapper.style.display = 'block';
    renderGraphAnalysis(data.graphAnalysis, graphContainer);
  } else if (graphWrapper) {
    graphWrapper.style.display = 'none';
  }

  // Answer
  if (!retrievalOnly && data.answer) {
    if (answerWrapper) answerWrapper.style.display = 'block';
    if (answerText) answerText.innerHTML = formatMarkdown(data.answer);

    if (citationsList) {
      let citHtml = '';
      (data.citations || []).forEach(c => {
        citHtml += `<a href="${c.url}" class="citation-pill" target="_blank">[${c.index}] ${escapeHtml(c.label)} (Score: ${c.score})</a>`;
      });
      citationsList.innerHTML = citHtml || '<span style="font-size: 0.75rem; color: #0F766E;">No external citations referenced.</span>';
    }
  } else {
    if (answerWrapper) answerWrapper.style.display = 'none';
  }

  // Evidence Chunks
  const evidence = data.evidence || [];
  if (evidenceCount) evidenceCount.textContent = `${evidence.length} chunks retrieved via ${(data.retrievalMethod || 'vector').toUpperCase()}`;

  if (!evidenceList) return;
  if (evidence.length === 0) {
    evidenceList.innerHTML = `
      <div style="padding: 24px; text-align: center; color: var(--color-text-muted);">
        Zero matching evidence chunks found under active role filter (<strong>${escapeHtml(data.role)}</strong>).
      </div>
    `;
    return;
  }

  let html = '';
  evidence.forEach(e => {
    const isConfidential = e.accessLevel !== 'public';
    let meterInfo = '';
    if (e.strategy === 'hybrid' || e.rrfScore !== undefined) {
      meterInfo = `RRF Score: ${e.score} (Vec Rank: #${e.vectorRank || '-'}, BM25 Rank: #${e.bm25Rank || '-'})`;
    } else if (e.retrievalMethod === 'bm25' || e.bm25Score !== undefined) {
      meterInfo = `BM25: ${e.score} (Matched: ${(e.matchedTerms || []).join(', ') || 'lexical'})`;
    } else {
      meterInfo = `Cosine: ${e.score.toFixed(4)} (${Math.round(e.score * 100)}%)`;
    }

    html += `
      <div class="evidence-card">
        <div class="evidence-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="badge ${isConfidential ? 'badge-danger' : 'badge-navy'}">Rank #${e.rank}</span>
            <span class="chunk-id-tag">${e.chunkId}</span>
            ${e.strategy === 'hybrid' ? '<span class="badge badge-gold" style="font-size:0.6875rem;">HYBRID RRF</span>' : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="score-meter">${meterInfo}</span>
            <span class="badge ${isConfidential ? 'badge-gold' : 'badge-teal'}">${e.accessLevel.toUpperCase()}</span>
          </div>
        </div>
        <div style="font-size: 0.8125rem; font-weight: 700; color: var(--color-navy); margin-bottom: 6px;">
          ${escapeHtml(e.sectionTitle || 'Section')} &bull; Source: <a href="${e.citation.url}" target="_blank" style="color: var(--color-teal); text-decoration: underline;">${escapeHtml(e.citation.label)}</a>
        </div>
        <div class="evidence-text">${escapeHtml(e.text)}</div>
      </div>
    `;
  });

  evidenceList.innerHTML = html;
}

function executeClientFallback(question, topK, strategy, role, retrievalOnly) {
  const match = goldenQuestions.find(q => q.question.toLowerCase().includes(question.toLowerCase()) || question.toLowerCase().includes(q.question.toLowerCase()));
  
  const mockEvidence = [];
  if (match && match.relevantDocIds) {
    match.relevantDocIds.slice(0, topK).forEach((did, idx) => {
      mockEvidence.push({
        rank: idx + 1,
        score: roundNumber(0.48 - idx * 0.05, 4),
        chunkId: `CHK-${did}-SEM-01`,
        docId: did,
        sourceId: match.relevantSourceIds[0] || 'CATALOG',
        accessLevel: match.authorizedRoles.includes('customer') ? 'public' : 'internal_procurement',
        sectionTitle: 'Verified Section',
        text: `[Grounded Reference Data for ${did}]\n${match.expectedAnswer}`,
        citation: {
          label: `Reference Dossier [${did}]`,
          url: `products.html?search=${match.relevantSourceIds[0] || ''}`
        }
      });
    });
  }

  const fallbackData = {
    question: question,
    role: role,
    strategy: strategy,
    retrievalMethod: 'hybrid_fallback',
    executionMode: 'offline_reference',
    latency: {
      embeddingMs: 1.2,
      retrievalMs: 24.5,
      generationMs: retrievalOnly ? 0 : 5.1,
      totalMs: retrievalOnly ? 25.7 : 30.8
    },
    answer: match ? match.expectedAnswer : `[Offline Reference Grounding]: The query "${question}" was analyzed. Run the backend server with 'python3 quirk-and-quanta/rag/server.py 8000' for dynamic vector ranking.`,
    citations: mockEvidence.map(e => ({
      index: e.rank,
      label: e.citation.label,
      url: e.citation.url,
      score: e.score
    })),
    evidence: mockEvidence
  };

  renderResults(fallbackData, retrievalOnly);
}

function formatMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\[SKU:\s*(QQ-[0-9]{4})\]/g, '<a href="product.html?sku=$1" class="citation-pill" target="_blank">SKU: $1</a>')
    .replace(/\[Doc:\s*(.*?)\]/g, '<span class="citation-pill">$1</span>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

function escapeHtml(text) {
  return (text || '').replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  })[m]);
}

function roundNumber(num, dec) {
  return Math.round(num * Math.pow(10, dec)) / Math.pow(10, dec);
}

function renderGraphAnalysis(analysis, container) {
  const skus = analysis.productsInvestigated || [];
  const findings = analysis.findings || [];
  const rootFound = analysis.rootCauseIdentified;

  let html = `
    <div style="font-size: 0.8125rem; margin-bottom: 12px; color: #78350F;">
      <strong>Investigated Products:</strong> ${skus.map(s => `<a href="product.html?sku=${s}" target="_blank" class="citation-pill" style="background:#FEF3C7; color:#92400E; border-color:#F59E0B;">${s}</a>`).join(' ')}
    </div>
  `;

  if (!rootFound || findings.length === 0) {
    html += `
      <div style="padding: 12px; background: #FFFBEB; border-radius: 4px; color: #92400E; font-size: 0.8125rem;">
        No common defect or recall notice links these products.
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  findings.forEach(f => {
    const compId = f.componentId;
    const compName = f.componentName;
    const recalls = f.recalls || [];
    const suppliers = f.suppliers || [];

    html += `
      <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 8px;">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <div style="background: #EFF6FF; border: 1px solid #93C5FD; border-radius: 6px; padding: 6px 12px; font-size: 0.75rem; font-weight: 700; color: #1E40AF;">
            📦 Products: ${skus.join(', ')}
          </div>
          <div style="color: #F59E0B; font-weight: 900; font-size: 0.875rem;">➔ [CONTAINS] ➔</div>
          <div style="background: #ECFDF5; border: 1px solid #6EE7B7; border-radius: 6px; padding: 6px 12px; font-size: 0.75rem; font-weight: 700; color: #065F46;">
            ⚙️ Component: ${compId} (${escapeHtml(compName)})
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-left: 20px;">
          <div style="color: #DC2626; font-weight: 900; font-size: 0.875rem;">➔ [AFFECTED_BY] ➔</div>
          ${recalls.map(r => `
            <div style="background: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 6px; padding: 8px 12px; font-size: 0.75rem; color: #991B1B;">
              <strong>🚨 Recall: ${r.recallId}</strong> &bull; Batch: <code>${r.batch}</code> &bull; Severity: <span class="badge badge-danger">${r.severity.toUpperCase()}</span><br>
              <span style="font-size: 0.6875rem; color: #7F1D1D;">${escapeHtml(r.title)}</span>
            </div>
          `).join('')}
        </div>

        ${suppliers.length > 0 ? `
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-left: 20px;">
            <div style="color: #6B7280; font-weight: 900; font-size: 0.875rem;">➔ [SUPPLIED_BY] ➔</div>
            ${suppliers.map(s => `
              <div style="background: #F3F4F6; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 12px; font-size: 0.75rem; color: #374151;">
                🏭 Supplier: <strong>${s.supplierId}</strong> (${escapeHtml(s.supplierName)})
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  });

  container.innerHTML = html;
}
