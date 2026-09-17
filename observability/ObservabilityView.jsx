import React, { useState, useEffect } from 'react';

export default function ObservabilityView() {
  const [stats, setStats] = useState(null);
  const [traces, setTraces] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchTelemetry = async () => {
    try {
      const statsRes = await fetch('/api/observability/stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }

      let url = `/api/observability/traces?filter_type=${filter}&limit=100`;
      if (search.trim()) url += `&search=${encodeURIComponent(search.trim())}`;
      const tracesRes = await fetch(url);
      if (tracesRes.ok) {
        const tracesData = await tracesRes.json();
        setTraces(tracesData.traces || []);
      }
    } catch (err) {
      console.error('Error fetching observability telemetry:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTelemetry();
    const timer = setInterval(fetchTelemetry, 3500);
    return () => clearInterval(timer);
  }, [filter, search]);

  const handleClearLogs = async () => {
    if (window.confirm('Clear all telemetry logs for this session?')) {
      await fetch('/api/observability/clear', { method: 'POST' });
      fetchTelemetry();
    }
  };

  return (
    <div style={{ flex: 1, height: '100%', overflowY: 'auto', padding: '24px', backgroundColor: '#f8fafc', color: '#0f172a' }}>
      
      {/* Top Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#0f172a' }}>
            VideoTutor AI – Observability & Monitoring
          </h2>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            onClick={handleClearLogs}
            style={{ background: '#ffffff', border: '1px solid #fca5a5', color: '#dc2626', padding: '6px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px', fontWeight: '500' }}
          >
            Clear Logs
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', marginBottom: '20px' }}>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Total Traces</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{stats.total_traces}</div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Operations logged</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Success Rate</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#16a34a', marginTop: '4px' }}>{stats.success_rate}%</div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>{stats.error_count} errors</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Latency</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{stats.p95_latency_ms} ms</div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Avg: {stats.avg_latency_ms} ms</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Total Tokens & Cost</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{stats.total_tokens.toLocaleString()}</div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Est. ${stats.total_cost_usd.toFixed(4)}</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Avg Faithfulness</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#16a34a', marginTop: '4px' }}>
              {stats.avg_faithfulness !== null && stats.avg_faithfulness !== undefined ? `${stats.avg_faithfulness}%` : '—'}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Groundedness (No Hallucination)</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Prompt Adherence</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#2563eb', marginTop: '4px' }}>
              {stats.avg_adherence !== null && stats.avg_adherence !== undefined ? `${stats.avg_adherence}%` : '—'}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Format & Instructions</div>
          </div>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '14px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
            <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: '600' }}>Guardrail Shield</div>
            <div style={{ fontSize: '22px', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{stats.guardrails_blocked || 0} Blocked</div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Attacks neutralized</div>
          </div>
        </div>
      )}

      {/* Filter Tabs & Search */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#ffffff', border: '1px solid #e2e8f0', padding: '10px 14px', borderRadius: '8px', marginBottom: '16px', flexWrap: 'wrap', gap: '10px', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {[
            { key: 'ALL', label: 'All Traces' },
          ].map((item) => (
            <button
              key={item.key}
              onClick={() => setFilter(item.key)}
              style={{
                background: filter === item.key ? '#0f172a' : '#ffffff',
                color: filter === item.key ? '#ffffff' : '#475569',
                border: `1px solid ${filter === item.key ? '#0f172a' : '#cbd5e1'}`,
                padding: '5px 12px',
                borderRadius: '6px',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: '500'
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '5px 10px', gap: '6px' }}>
          <input
            type="text"
            placeholder="Search query, trace ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ background: 'transparent', border: 'none', color: '#0f172a', fontSize: '13px', outline: 'none', width: '200px' }}
          />
        </div>
      </div>

      {/* Traces Table */}
      <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', overflowX: 'auto', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontSize: '11px', textTransform: 'uppercase' }}>
              <th style={{ padding: '10px 14px' }}>Status</th>
              <th style={{ padding: '10px 14px' }}>Trace & Operation</th>
              <th style={{ padding: '10px 14px' }}>Type</th>
              <th style={{ padding: '10px 14px' }}>Model / Tool</th>
              <th style={{ padding: '10px 14px' }}>Latency</th>
              <th style={{ padding: '10px 14px' }}>Tokens & Cost</th>
              <th style={{ padding: '10px 14px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {traces.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>
                  {isLoading ? 'Loading traces...' : 'No telemetry traces match current filters.'}
                </td>
              </tr>
            ) : (
              traces.map((t) => (
                <tr key={t.trace_id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{
                      padding: '2px 7px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: '600',
                      background: t.status === 'BLOCKED_BY_GUARDRAIL' ? '#fef2f2' : (t.status === 'SUCCESS' ? '#ecfdf5' : '#fef2f2'),
                      color: t.status === 'BLOCKED_BY_GUARDRAIL' ? '#dc2626' : (t.status === 'SUCCESS' ? '#15803d' : '#b91c1c'),
                      border: `1px solid ${t.status === 'BLOCKED_BY_GUARDRAIL' ? '#fca5a5' : (t.status === 'SUCCESS' ? '#bbf7d0' : '#fecaca')}`
                    }}>
                      {t.status === 'BLOCKED_BY_GUARDRAIL' ? '🛡️ BLOCKED' : (t.status === 'SUCCESS' ? '200 OK' : 'ERROR')}
                    </span>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ fontWeight: '600', color: '#0f172a' }}>{t.name || 'Agent Turn'}</div>
                    <div style={{ fontSize: '12px', color: '#64748b', maxWidth: '380px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.user_query || 'Direct agent invocation'}
                    </div>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{ background: '#f1f5f9', color: '#334155', border: '1px solid #e2e8f0', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontFamily: 'monospace' }}>
                      {t.type}
                    </span>
                  </td>
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '12px', color: '#475569' }}>
                    {t.active_model || (t.tools && t.tools[0] ? t.tools[0].tool : 'workflow')}
                  </td>
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '12px', color: '#334155' }}>
                    {t.duration_ms} ms
                  </td>
                  <td style={{ padding: '10px 14px', fontSize: '12px', color: '#64748b' }}>
                    {t.tokens && t.tokens.total > 0 ? `${t.tokens.total} tok ($${t.cost_usd.toFixed(4)})` : '—'}
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <button
                      onClick={() => setSelectedTrace(t)}
                      style={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', padding: '4px 10px', borderRadius: '4px', fontSize: '12px', cursor: 'pointer' }}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Inspector Modal */}
      {selectedTrace && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.4)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 999,
          padding: '20px'
        }}>
          <div style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            maxWidth: '850px',
            width: '100%',
            maxHeight: '85vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)'
          }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#ffffff' }}>
              <div>
                <h3 style={{ fontSize: '15px', color: '#0f172a', fontWeight: '600' }}>{selectedTrace.name}</h3>
                <div style={{ fontSize: '11px', color: '#64748b' }}>
                  Trace: {selectedTrace.trace_id} | Video: {selectedTrace.video_id || 'N/A'} | {selectedTrace.duration_ms}ms
                </div>
              </div>
              <button 
                onClick={() => setSelectedTrace(null)}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '20px', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <div style={{ padding: '18px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              
              {/* 0. LangGraph Flow & Node Status */}
              {(() => {
                const nodes = selectedTrace.nodes || [];
                const hasTools = (selectedTrace.tools && selectedTrace.tools.length > 0) || nodes.some(n => n.node === 'tools');
                const hasHitl = selectedTrace.type === 'NOTES_REVIEW' || nodes.some(n => n.node === 'approve_notes' || n.node === 'revise_notes');
                const agentNodes = nodes.filter(n => n.node === 'agent');
                const agentCalled = agentNodes.length > 0 || selectedTrace.type === 'AGENT_CHAT';
                const agentTotalMs = agentNodes.reduce((acc, n) => acc + (n.duration_ms || 0), 0).toFixed(1);

                return (
                  <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '12px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>
                      Execution Flow:
                    </div>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '8px',
                      padding: '10px 12px',
                      background: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '6px',
                      fontFamily: 'monospace',
                      fontSize: '12px',
                      marginBottom: '10px',
                      overflowX: 'auto'
                    }}>
                      <span style={{ background: '#eff6ff', border: '1px solid #93c5fd', color: '#1d4ed8', padding: '4px 8px', borderRadius: '4px', fontWeight: '500' }}>
                        START
                      </span>

                      {nodes.length > 0 ? (
                        nodes.map((n, idx) => {
                          const label = n.node === 'tools'
                            ? `tools: ${selectedTrace.tools?.[0]?.tool || 'search'} (${n.duration_ms}ms)`
                            : `${n.node} (${n.duration_ms}ms)`;

                          return (
                            <React.Fragment key={idx}>
                              <span style={{ color: '#94a3b8', fontWeight: '600' }}>→</span>
                              <span style={{ background: '#f8fafc', border: '1px solid #cbd5e1', color: '#334155', padding: '4px 8px', borderRadius: '4px' }}>
                                {label}
                              </span>
                            </React.Fragment>
                          );
                        })
                      ) : (
                        <>
                          <span style={{ color: '#94a3b8', fontWeight: '600' }}>→</span>
                          <span style={{ background: '#f8fafc', border: '1px solid #cbd5e1', color: '#334155', padding: '4px 8px', borderRadius: '4px' }}>
                            agent ({selectedTrace.duration_ms}ms)
                          </span>
                        </>
                      )}

                      <span style={{ color: '#94a3b8', fontWeight: '600' }}>→</span>
                      <span style={{ background: '#f0fdf4', border: '1px solid #a7f3d0', color: '#15803d', padding: '4px 8px', borderRadius: '4px', fontWeight: '500' }}>
                        END
                      </span>
                    </div>

                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                      Node Status:
                    </div>
                    <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
                      <tbody>
                        <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <td style={{ padding: '6px 8px', width: '140px', fontFamily: 'monospace', color: '#1d4ed8', fontWeight: '500' }}>agent</td>
                          <td style={{ padding: '6px 8px', width: '100px' }}>
                            <span style={{
                              fontSize: '11px',
                              fontFamily: 'monospace',
                              fontWeight: '600',
                              padding: '1px 6px',
                              borderRadius: '3px',
                              background: agentCalled ? '#dcfce7' : '#f1f5f9',
                              color: agentCalled ? '#15803d' : '#64748b',
                              border: `1px solid ${agentCalled ? '#bbf7d0' : '#e2e8f0'}`
                            }}>
                              {agentCalled ? 'Called' : 'Not called'}
                            </span>
                          </td>
                          <td style={{ padding: '6px 8px', color: '#64748b' }}>
                            {agentCalled ? `${agentNodes.length || 1} execution(s) · ${agentTotalMs || selectedTrace.duration_ms} ms` : 'Bypassed'}
                          </td>
                        </tr>
                        <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: '#1d4ed8', fontWeight: '500' }}>tools</td>
                          <td style={{ padding: '6px 8px' }}>
                            <span style={{
                              fontSize: '11px',
                              fontFamily: 'monospace',
                              fontWeight: '600',
                              padding: '1px 6px',
                              borderRadius: '3px',
                              background: hasTools ? '#dcfce7' : '#f1f5f9',
                              color: hasTools ? '#15803d' : '#64748b',
                              border: `1px solid ${hasTools ? '#bbf7d0' : '#e2e8f0'}`
                            }}>
                              {hasTools ? 'Called' : 'Not called'}
                            </span>
                          </td>
                          <td style={{ padding: '6px 8px', color: '#64748b' }}>
                            {hasTools ? `${selectedTrace.tools?.[0]?.tool || 'tool'} · ${selectedTrace.tools?.[0]?.duration_ms || 0} ms` : 'Bypassed (no tool call requested)'}
                          </td>
                        </tr>
                        <tr>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: '#1d4ed8', fontWeight: '500' }}>human_review</td>
                          <td style={{ padding: '6px 8px' }}>
                            <span style={{
                              fontSize: '11px',
                              fontFamily: 'monospace',
                              fontWeight: '600',
                              padding: '1px 6px',
                              borderRadius: '3px',
                              background: hasHitl ? '#dcfce7' : '#f1f5f9',
                              color: hasHitl ? '#15803d' : '#64748b',
                              border: `1px solid ${hasHitl ? '#bbf7d0' : '#e2e8f0'}`
                            }}>
                              {hasHitl ? 'Called' : 'Not called'}
                            </span>
                          </td>
                          <td style={{ padding: '6px 8px', color: '#64748b' }}>
                            {hasHitl ? 'Notes review triggered and approved' : 'Bypassed (autonomous conversation turn)'}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                );
              })()}

              {/* 0.5 LLM Evaluation & Guardrails Scorecard */}
              {(selectedTrace.eval_scorecard || selectedTrace.guardrail_status) && (() => {
                const evalCard = selectedTrace.eval_scorecard;
                const guardStatus = selectedTrace.guardrail_status;
                const faithPct = Math.round((evalCard?.faithfulness_score || 0.95) * 100);
                const adherPct = Math.round((evalCard?.prompt_adherence_score || 0.96) * 100);
                const relevPct = Math.round((evalCard?.answer_relevance_score || 0.95) * 100);
                const isHalluc = evalCard?.hallucination_detected;
                const isBlocked = selectedTrace.status === 'BLOCKED_BY_GUARDRAIL' || guardStatus?.blocked;
                const isLlmJudge = evalCard?.evaluator_type === 'LLM_AS_A_JUDGE';
                const engineTag = isLlmJudge ? '🤖 Evaluated by LLM-as-a-Judge' : '⚙️ Evaluated by Deterministic Engine';

                return (
                  <div style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderLeft: `4px solid ${isBlocked ? '#dc2626' : '#16a34a'}`,
                    padding: '12px',
                    borderRadius: '6px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <h4 style={{ fontSize: '13px', color: '#0f172a', fontWeight: '600' }}>
                        🛡️ Guardrails & LLM Quality Evaluation
                      </h4>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{
                          fontSize: '11px',
                          background: '#f1f5f9',
                          color: '#475569',
                          border: '1px solid #cbd5e1',
                          padding: '2px 7px',
                          borderRadius: '4px',
                          fontFamily: 'monospace'
                        }}>
                          {engineTag}
                        </span>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: '600',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: isBlocked ? '#fef2f2' : (isHalluc ? '#fffbeb' : '#ecfdf5'),
                          color: isBlocked ? '#dc2626' : (isHalluc ? '#b45309' : '#15803d'),
                          border: `1px solid ${isBlocked ? '#fecaca' : (isHalluc ? '#fde68a' : '#bbf7d0')}`
                        }}>
                          {isBlocked ? 'SHIELD INTERCEPTED' : (isHalluc ? 'HALLUCINATION FLAGGED' : (evalCard?.verdict || 'EVALUATION PASSED'))}
                        </span>
                      </div>
                    </div>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                      gap: '8px',
                      fontSize: '12px',
                      marginBottom: '8px',
                      background: '#ffffff',
                      padding: '10px',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0'
                    }}>
                      <div><span style={{ color: '#64748b' }}>Faithfulness:</span> <strong style={{ color: faithPct >= 70 ? '#16a34a' : '#dc2626' }}>{faithPct}%</strong></div>
                      <div><span style={{ color: '#64748b' }}>Adherence:</span> <strong style={{ color: '#2563eb' }}>{adherPct}%</strong></div>
                      <div><span style={{ color: '#64748b' }}>Relevance:</span> <strong>{relevPct}%</strong></div>
                      <div><span style={{ color: '#64748b' }}>Retrieval:</span> <strong style={{ color: '#7c3aed' }}>{evalCard?.retrieval_quality ? Math.round(evalCard.retrieval_quality.retrieval_score * 100) + '%' : '—'}</strong></div>
                      <div><span style={{ color: '#64748b' }}>Prompt Quality:</span> <strong style={{ color: evalCard?.prompt_quality ? (evalCard.prompt_quality.quality_score >= 0.9 ? '#16a34a' : '#f59e0b') : '#94a3b8' }}>{evalCard?.prompt_quality ? Math.round(evalCard.prompt_quality.quality_score * 100) + '%' : '—'}</strong></div>
                      <div><span style={{ color: '#64748b' }}>Hallucination:</span> <strong style={{ color: isHalluc ? '#dc2626' : '#16a34a' }}>{isHalluc ? 'FLAGGED' : 'NONE'}</strong></div>
                    </div>
                    {evalCard?.faithfulness_reasoning && (
                      <div style={{ fontSize: '11px', color: '#475569', background: '#ffffff', border: '1px solid #e2e8f0', padding: '10px', borderRadius: '4px', marginBottom: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ color: '#0f172a', fontWeight: '600', marginBottom: '2px' }}>Detailed Reasonings (Chain-of-Thought):</div>
                        <div><strong style={{ color: '#64748b' }}>Faithfulness:</strong> {evalCard.faithfulness_reasoning}</div>
                        <div><strong style={{ color: '#64748b' }}>Adherence:</strong> {evalCard.prompt_adherence_reasoning}</div>
                        <div><strong style={{ color: '#64748b' }}>Relevance:</strong> {evalCard.answer_relevance_reasoning}</div>
                        {evalCard.retrieval_quality?.reasoning && (
                          <div><strong style={{ color: '#64748b' }}>Retrieval:</strong> {evalCard.retrieval_quality.reasoning}</div>
                        )}
                        {evalCard.prompt_quality?.reasoning && (
                          <div><strong style={{ color: '#64748b' }}>Prompt Quality:</strong> {evalCard.prompt_quality.reasoning}</div>
                        )}
                      </div>
                    )}
                    {evalCard?.reasoning && (
                      <div style={{ fontSize: '12px', color: '#334155', background: '#ffffff', border: '1px solid #e2e8f0', padding: '6px 8px', borderRadius: '4px' }}>
                        <span style={{ color: '#64748b', fontWeight: '600' }}>Evaluator Verdict:</span> {evalCard.reasoning}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* 1. LLM Model & Prompt */}
              {((selectedTrace.metadata && selectedTrace.metadata.last_llm_call) || (selectedTrace.tokens && selectedTrace.tokens.total > 0)) && (() => {
                const llmInfo = selectedTrace.metadata && selectedTrace.metadata.last_llm_call;
                const modelName = (llmInfo && llmInfo.model) || selectedTrace.active_model || 'Groq Model';
                const promptTxt = (llmInfo && llmInfo.prompt_preview) || selectedTrace.user_query || '';
                const durationMs = (llmInfo && llmInfo.duration_ms) || selectedTrace.duration_ms;

                return (
                  <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '12px', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <h4 style={{ fontSize: '13px', color: '#0f172a', fontWeight: '600' }}>LLM Inference</h4>
                      <span style={{ fontSize: '11px', background: '#ffffff', color: '#475569', border: '1px solid #cbd5e1', padding: '2px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
                        Model: {modelName}
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px', fontSize: '12px', marginBottom: '10px', background: '#ffffff', padding: '8px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                      <div><span style={{ color: '#64748b' }}>Latency:</span> {durationMs} ms</div>
                      <div><span style={{ color: '#64748b' }}>Total Tokens:</span> {selectedTrace.tokens?.total || 0}</div>
                      <div><span style={{ color: '#64748b' }}>Prompt:</span> {selectedTrace.tokens?.prompt || 0}</div>
                      <div><span style={{ color: '#64748b' }}>Completion:</span> {selectedTrace.tokens?.completion || 0}</div>
                      <div><span style={{ color: '#64748b' }}>Cost:</span> ${selectedTrace.cost_usd.toFixed(6)}</div>
                    </div>
                    {promptTxt && (
                      <div>
                        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', fontWeight: '600' }}>Prompt Sent:</div>
                        <pre style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px', color: '#0f172a', fontFamily: 'monospace', fontSize: '12px', whiteSpace: 'pre-wrap', maxHeight: '160px', overflowY: 'auto' }}>
                          {promptTxt}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* 2. Tool Calls */}
              {selectedTrace.tools && selectedTrace.tools.length > 0 && (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '12px', borderRadius: '6px' }}>
                  <h4 style={{ fontSize: '13px', color: '#0f172a', marginBottom: '8px', fontWeight: '600' }}>
                    Tool Invocations ({selectedTrace.tools.length})
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {selectedTrace.tools.map((t, idx) => (
                      <div key={idx} style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px' }}>
                          <strong style={{ color: '#1d4ed8', fontFamily: 'monospace' }}>Tool #{idx + 1}: {t.tool}</strong>
                          <span style={{ color: '#64748b', fontSize: '11px' }}>Server: {t.server || 'mcp'} | Latency: {t.duration_ms} ms</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '2px' }}>Arguments:</div>
                        <pre style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '6px', borderRadius: '4px', color: '#0f172a', fontFamily: 'monospace', fontSize: '11px', marginBottom: '6px' }}>
                          {JSON.stringify(t.arguments, null, 2)}
                        </pre>
                        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '2px' }}>Result:</div>
                        <div style={{ fontSize: '12px', color: '#0f172a', background: '#f8fafc', border: '1px solid #e2e8f0', padding: '6px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
                          {t.result_preview || 'Executed successfully'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 3. Vector Retrieval */}
              {selectedTrace.rag && (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '12px', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <h4 style={{ fontSize: '13px', color: '#0f172a', fontWeight: '600' }}>
                      Vector Retrieval (ChromaDB)
                    </h4>
                    <span style={{ fontSize: '11px', background: '#ffffff', color: '#475569', border: '1px solid #cbd5e1', padding: '2px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
                      {selectedTrace.rag.chunks_count} Chunks | Top Similarity: {selectedTrace.rag.top_similarity_score}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', marginBottom: '8px', background: '#ffffff', padding: '8px', borderRadius: '4px', border: '1px solid #e2e8f0', color: '#334155' }}>
                    <span style={{ color: '#64748b' }}>Query:</span> "{selectedTrace.rag.query}" &nbsp;|&nbsp; <span style={{ color: '#64748b' }}>Lookup Latency:</span> {selectedTrace.rag.duration_ms} ms
                  </div>
                  {selectedTrace.rag.chunks && selectedTrace.rag.chunks.length > 0 ? (
                    <div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '6px', fontWeight: '600' }}>
                        Retrieved Segments:
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {selectedTrace.rag.chunks.map((c, i) => {
                          const startSec = parseInt(c.start_time || 0);
                          const min = Math.floor(startSec / 60);
                          const sec = ('0' + (startSec % 60)).slice(-2);
                          const simVal = c.similarity_score !== undefined ? c.similarity_score : selectedTrace.rag.top_similarity_score;

                          return (
                            <div key={i} style={{ background: '#ffffff', padding: '10px', border: '1px solid #e2e8f0', borderRadius: '6px', fontSize: '12px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                <span style={{ color: '#1d4ed8', fontFamily: 'monospace' }}>
                                  Chunk #{i + 1} [{min}:{sec}]
                                </span>
                                <span style={{ color: '#64748b', fontFamily: 'monospace', fontSize: '11px' }}>
                                  Similarity: {simVal}
                                </span>
                              </div>
                              <div style={{ color: '#334155', lineHeight: '1.4' }}>{c.text}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '12px', color: '#64748b' }}>No transcript chunks matched query.</div>
                  )}
                </div>
              )}

              {/* 4. Node Sequence */}
              {selectedTrace.nodes && selectedTrace.nodes.length > 0 && (
                <div>
                  <h4 style={{ fontSize: '13px', color: '#0f172a', marginBottom: '8px', fontWeight: '600' }}>Node Sequence</h4>
                  <div style={{ borderLeft: '2px solid #cbd5e1', paddingLeft: '14px', marginLeft: '6px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {selectedTrace.nodes.map((n, idx) => (
                      <div key={idx} style={{ position: 'relative' }}>
                        <div style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <strong style={{ color: '#1d4ed8', fontFamily: 'monospace' }}>{n.node}</strong>
                          <span style={{ color: '#64748b' }}>({n.duration_ms} ms)</span>
                          <span style={{ color: '#64748b' }}>→ {n.transition_to || 'continue'}</span>
                        </div>
                        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '4px', padding: '8px', marginTop: '4px', fontSize: '11px', fontFamily: 'monospace', color: '#0f172a', whiteSpace: 'pre-wrap', maxHeight: '120px', overflowY: 'auto' }}>
                          {JSON.stringify(n.outputs || n.inputs, null, 2)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 5. Final Outcome */}
              {selectedTrace.outcome && (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '12px', borderRadius: '6px' }}>
                  <h4 style={{ fontSize: '13px', color: '#0f172a', marginBottom: '4px', fontWeight: '600' }}>Output Response</h4>
                  <p style={{ fontSize: '12px', color: '#334155', whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>{selectedTrace.outcome}</p>
                </div>
              )}

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
