"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  checkBackendHealth,
  listProjects,
  createProject,
  getProject,
  uploadProjectFiles,
  getFileContent,
  saveProjectContext,
  getProjectContext,
  clearProjectContext,
  askProjectQuestion,
  runEvaluation,
  listEvaluationRuns,
  getEvaluationRun,
  getEvaluationDataset,
  getIndexStatus,
  indexProjectCodebase,
  searchProjectContext,
  deleteProjectIndex,
  deleteProject,
  Project,
  FileContentResponse,
  ContextFileSelection,
  ContextResponse,
  ChatResponse,
  CitationItem,
  SkippedFileWarning,
  EvalRunResponse,
  EvalDatasetResponse,
  IndexStatusResponse,
  SearchResultItem,
  SemanticSearchResponse,
  API_BASE_URL,
} from "@/lib/api";

type ConnectionStatus = "checking" | "connected" | "disconnected";
type WorkspaceTab = "viewer" | "discovery" | "chat";
type MainNavTab = "dashboard" | "projects" | "context" | "evaluation" | "settings";

export default function Home() {
  // Navigation & View state
  const [activeTab, setActiveTab] = useState<MainNavTab>("dashboard");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("viewer");

  // Backend Connection
  const [status, setStatus] = useState<ConnectionStatus>("checking");

  // Projects State
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);

  // Create Project Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Project Workspace Details
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [fileSearchQuery, setFileSearchQuery] = useState("");

  // File Upload State
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<FileList | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccessMsg, setUploadSuccessMsg] = useState<string | null>(null);
  const [uploadErrorMsg, setUploadErrorMsg] = useState<string | null>(null);
  const [uploadWarnings, setUploadWarnings] = useState<SkippedFileWarning[]>([]);

  // File Viewer & Context Selection State
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [fileContentData, setFileContentData] = useState<FileContentResponse | null>(null);
  const [loadingFileContent, setLoadingFileContent] = useState(false);
  const [fileContentError, setFileContentError] = useState<string | null>(null);

  // Local Context Selections map
  const [contextSelections, setContextSelections] = useState<Record<string, ContextFileSelection>>({});
  const [savedContext, setSavedContext] = useState<ContextResponse | null>(null);
  const [isSavingContext, setIsSavingContext] = useState(false);
  const [contextFeedback, setContextFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Line range form state for current viewed file
  const [rangeStartInput, setRangeStartInput] = useState<number>(1);
  const [rangeEndInput, setRangeEndInput] = useState<number>(1);

  // Phase 5: Chat & Gemini State
  const [questionInput, setQuestionInput] = useState("");
  const [isAskingQuestion, setIsAskingQuestion] = useState(false);
  const [chatHistory, setChatHistory] = useState<ChatResponse[]>([]);
  const [chatError, setChatError] = useState<string | null>(null);

  // Phase 6: Evaluation Dashboard State
  const [evalRuns, setEvalRuns] = useState<any[]>([]);
  const [activeEvalRun, setActiveEvalRun] = useState<EvalRunResponse | null>(null);
  const [datasetInfo, setDatasetInfo] = useState<EvalDatasetResponse | null>(null);
  const [isRunningEval, setIsRunningEval] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evalModesSelected, setEvalModesSelected] = useState<string[]>([
    "baseline",
    "context_lock",
    "context_lock_citations",
  ]);
  const [useMockEval, setUseMockEval] = useState(true);
  const [evalFilterMode, setEvalFilterMode] = useState<string>("all");

  // Phase 7: Semantic Discovery & pgvector State
  const [indexStatus, setIndexStatus] = useState<IndexStatusResponse | null>(null);
  const [loadingIndexStatus, setLoadingIndexStatus] = useState(false);
  const [isIndexingCodebase, setIsIndexingCodebase] = useState(false);
  const [indexingFeedback, setIndexingFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [semanticQuery, setSemanticQuery] = useState("");
  const [isSearchingContext, setIsSearchingContext] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searchDisclaimer, setSearchDisclaimer] = useState<string | null>(null);
  const [searchErrorMsg, setSearchErrorMsg] = useState<string | null>(null);
  const [useMockDiscovery, setUseMockDiscovery] = useState(false);

  // Phase 9: Context Preview & Estimated Token Count Modal
  const [showContextPreviewModal, setShowContextPreviewModal] = useState(false);

  // 1. Verify backend health
  const verifyConnection = useCallback(async () => {
    setStatus("checking");
    const result = await checkBackendHealth();
    if (result.success && result.data) {
      setStatus("connected");
    } else {
      setStatus("disconnected");
    }
  }, []);

  // 2. Load projects
  const fetchProjects = useCallback(async () => {
    setLoadingProjects(true);
    const res = await listProjects();
    if (res.success && res.data) {
      setProjects(res.data.projects);
    }
    setLoadingProjects(false);
  }, []);

  // Stable refs to prevent cascading re-renders and flicker
  const contextSelectionsRef = useRef(contextSelections);
  useEffect(() => {
    contextSelectionsRef.current = contextSelections;
  }, [contextSelections]);

  const projectsRef = useRef(projects);
  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  // 3. Load active project details and saved context
  const fetchActiveProjectData = useCallback(async (id: string) => {
    const projRes = await getProject(id);
    if (projRes.success && projRes.data) {
      setActiveProject(projRes.data);
      if (projRes.data.files && projRes.data.files.length > 0) {
        setSelectedFileId((prev) => {
          const exists = projRes.data?.files?.some((f) => f.id === prev);
          return exists ? prev : (projRes.data?.files?.[0]?.id ?? null);
        });
      }
    }

    const ctxRes = await getProjectContext(id);
    if (ctxRes.success && ctxRes.data) {
      setSavedContext(ctxRes.data);
      const selMap: Record<string, ContextFileSelection> = {};
      for (const item of ctxRes.data.selected_files) {
        selMap[item.file_id] = {
          file_id: item.file_id,
          selected_all_lines: item.selected_all_lines,
          line_range:
            !item.selected_all_lines && item.start_line && item.end_line
              ? { start_line: item.start_line, end_line: item.end_line }
              : null,
        };
      }
      setContextSelections(selMap);
    }

    // Load Phase 7 index status
    const idxRes = await getIndexStatus(id, useMockDiscovery);
    if (idxRes.success && idxRes.data) {
      setIndexStatus(idxRes.data);
    }
  }, [useMockDiscovery]);

  // 4. Load evaluations
  const fetchEvaluationData = useCallback(async () => {
    const dsRes = await getEvaluationDataset();
    if (dsRes.success && dsRes.data) {
      setDatasetInfo(dsRes.data);
    }

    const runsRes = await listEvaluationRuns();
    if (runsRes.success && runsRes.data) {
      setEvalRuns(runsRes.data);
      if (runsRes.data.length > 0) {
        const latestRunId = runsRes.data[0].id;
        const detailRes = await getEvaluationRun(latestRunId);
        if (detailRes.success && detailRes.data) {
          setActiveEvalRun(detailRes.data);
        }
      }
    }
  }, []);

  // Initial load
  useEffect(() => {
    verifyConnection();
    fetchProjects();
    fetchEvaluationData();
  }, [verifyConnection, fetchProjects, fetchEvaluationData]);

  // When selected project changes
  useEffect(() => {
    if (selectedProjectId) {
      const cached = projectsRef.current.find((p) => p.id === selectedProjectId);
      if (cached) {
        setActiveProject((prev) => (prev?.id === selectedProjectId ? prev : cached));
      }
      setContextFeedback(null);
      setChatError(null);
      setWorkspaceTab("viewer");
      fetchActiveProjectData(selectedProjectId);
    } else {
      setActiveProject(null);
      setSelectedFileId(null);
      setFileContentData(null);
      setSavedContext(null);
      setContextSelections({});
      setChatHistory([]);
    }
  }, [selectedProjectId, fetchActiveProjectData]);

  // When selected file changes
  useEffect(() => {
    if (selectedProjectId && selectedFileId) {
      setLoadingFileContent(true);
      setFileContentError(null);

      let isCancelled = false;
      getFileContent(selectedProjectId, selectedFileId).then((res) => {
        if (isCancelled) return;
        if (res.success && res.data) {
          setFileContentData(res.data);
          const existingSel = contextSelectionsRef.current[selectedFileId];
          if (existingSel && !existingSel.selected_all_lines && existingSel.line_range) {
            setRangeStartInput(existingSel.line_range.start_line);
            setRangeEndInput(existingSel.line_range.end_line);
          } else {
            setRangeStartInput(1);
            setRangeEndInput(res.data.line_count || 1);
          }
        } else {
          setFileContentError(res.error || "Failed to load file content");
        }
        setLoadingFileContent(false);
      });

      return () => {
        isCancelled = true;
      };
    }
  }, [selectedProjectId, selectedFileId]);

  // Create Project
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) {
      setCreateError("Please enter a project name.");
      return;
    }

    setIsCreatingProject(true);
    setCreateError(null);

    const res = await createProject(newProjectName.trim());
    if (res.success && res.data) {
      setNewProjectName("");
      setShowCreateModal(false);
      await fetchProjects();
      setSelectedProjectId(res.data.id);
    } else {
      setCreateError(res.error || "Failed to create project");
    }
    setIsCreatingProject(false);
  };

  // Upload Files
  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !selectedUploadFiles || selectedUploadFiles.length === 0) {
      setUploadErrorMsg("Please choose files or a ZIP archive to upload.");
      return;
    }

    setIsUploading(true);
    setUploadSuccessMsg(null);
    setUploadErrorMsg(null);
    setUploadWarnings([]);

    const fileListArray = Array.from(selectedUploadFiles);
    const res = await uploadProjectFiles(selectedProjectId, fileListArray);

    if (res.success && res.data) {
      setUploadSuccessMsg(res.data.message);
      setUploadWarnings(res.data.skipped_files || []);
      setSelectedUploadFiles(null);
      const inputEl = document.getElementById("file-upload-input") as HTMLInputElement;
      if (inputEl) inputEl.value = "";
      await fetchActiveProjectData(selectedProjectId);
      await fetchProjects();
    } else {
      setUploadErrorMsg(res.error || "Upload failed. Please check file types and limits.");
    }
    setIsUploading(false);
  };

  // Toggle file-level context selection
  const handleToggleFileSelection = (fileId: string) => {
    setContextSelections((prev) => {
      const next = { ...prev };
      if (next[fileId]) {
        delete next[fileId];
      } else {
        next[fileId] = {
          file_id: fileId,
          selected_all_lines: true,
          line_range: null,
        };
      }
      return next;
    });
  };

  // Toggle all lines vs custom line range
  const handleToggleAllLinesForCurrentFile = (allLines: boolean) => {
    if (!selectedFileId || !fileContentData) return;
    setContextSelections((prev) => {
      const next = { ...prev };
      if (allLines) {
        next[selectedFileId] = {
          file_id: selectedFileId,
          selected_all_lines: true,
          line_range: null,
        };
      } else {
        const start = Math.max(1, rangeStartInput);
        const end = Math.min(fileContentData.line_count, Math.max(start, rangeEndInput));
        next[selectedFileId] = {
          file_id: selectedFileId,
          selected_all_lines: false,
          line_range: { start_line: start, end_line: end },
        };
      }
      return next;
    });
  };

  // Apply custom line range
  const handleApplyLineRange = () => {
    if (!selectedFileId || !fileContentData) return;
    const start = Math.max(1, rangeStartInput);
    const end = Math.min(fileContentData.line_count, Math.max(start, rangeEndInput));

    setContextSelections((prev) => ({
      ...prev,
      [selectedFileId]: {
        file_id: selectedFileId,
        selected_all_lines: false,
        line_range: { start_line: start, end_line: end },
      },
    }));

    setContextFeedback({
      type: "success",
      message: `Updated line range for ${fileContentData.filename} (lines ${start}–${end}). Click 'Lock Context' to save.`,
    });
  };

  // Save context selection to backend
  const handleSaveContext = async () => {
    if (!selectedProjectId) return;
    setIsSavingContext(true);
    setContextFeedback(null);

    const selectionsArray = Object.values(contextSelections);
    const res = await saveProjectContext(selectedProjectId, selectionsArray);

    if (res.success && res.data) {
      setSavedContext(res.data);
      setContextFeedback({
        type: "success",
        message: `Context locked: ${res.data.total_selected_files} files, ${res.data.total_selected_lines} lines ready for AI evidence.`,
      });
    } else {
      setContextFeedback({
        type: "error",
        message: res.error || "Failed to save context selection",
      });
    }
    setIsSavingContext(false);
  };

  // Clear context
  const handleClearContext = async () => {
    if (!selectedProjectId) return;
    const res = await clearProjectContext(selectedProjectId);
    if (res.success) {
      setContextSelections({});
      setSavedContext(null);
      setContextFeedback({
        type: "success",
        message: "Context scope cleared. No files are currently attached as AI evidence.",
      });
    } else {
      setContextFeedback({
        type: "error",
        message: res.error || "Failed to clear context",
      });
    }
  };

  // Ask Gemini with Context Lock
  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !questionInput.trim()) return;

    const selectionsArray = Object.values(contextSelections);
    if (selectionsArray.length === 0) {
      setChatError("No context selected. Please select files or line ranges to lock context before asking a question.");
      return;
    }

    setIsAskingQuestion(true);
    setChatError(null);

    const res = await askProjectQuestion(
      selectedProjectId,
      questionInput.trim(),
      selectionsArray
    );

    if (res.success && res.data) {
      setChatHistory((prev) => [res.data!, ...prev]);
      setQuestionInput("");
    } else {
      setChatError(res.error || "Failed to receive response from Gemini.");
    }
    setIsAskingQuestion(false);
  };

  // Jump from citation click directly into File Viewer
  const handleJumpToCitation = (citation: CitationItem) => {
    if (citation.source_id && activeProject?.files) {
      setSelectedFileId(citation.source_id);
      setRangeStartInput(citation.start_line);
      setRangeEndInput(citation.end_line);
      setWorkspaceTab("viewer");
    }
  };

  // Run Evaluation Handler
  const handleRunEvaluation = async () => {
    if (evalModesSelected.length === 0) {
      setEvalError("Please select at least one evaluation mode.");
      return;
    }

    setIsRunningEval(true);
    setEvalError(null);

    const res = await runEvaluation({
      modes: evalModesSelected,
      use_mock: useMockEval,
    });

    if (res.success && res.data) {
      setActiveEvalRun(res.data);
      await fetchEvaluationData();
    } else {
      setEvalError(res.error || "Evaluation run failed.");
    }
    setIsRunningEval(false);
  };

  // Select historical run
  const handleSelectRun = async (runId: string) => {
    const res = await getEvaluationRun(runId);
    if (res.success && res.data) {
      setActiveEvalRun(res.data);
    }
  };

  // Phase 7: Semantic Discovery Handlers
  const fetchIndexStatus = useCallback(async (projId: string, mockMode: boolean = false) => {
    setLoadingIndexStatus(true);
    const res = await getIndexStatus(projId, mockMode);
    if (res.success && res.data) {
      setIndexStatus(res.data);
    }
    setLoadingIndexStatus(false);
  }, []);

  const handleIndexCodebase = async (force: boolean = false) => {
    if (!selectedProjectId) return;
    setIsIndexingCodebase(true);
    setIndexingFeedback(null);

    const res = await indexProjectCodebase(selectedProjectId, force, useMockDiscovery);
    if (res.success && res.data) {
      setIndexingFeedback({
        type: "success",
        message: `${res.data.message} (${res.data.indexed_chunks} chunks indexed with ${res.data.embedding_model}).`,
      });
      await fetchIndexStatus(selectedProjectId, useMockDiscovery);
    } else {
      setIndexingFeedback({
        type: "error",
        message: res.error || "Indexing failed.",
      });
    }
    setIsIndexingCodebase(false);
  };

  const handleSearchContext = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !semanticQuery.trim()) return;

    setIsSearchingContext(true);
    setSearchErrorMsg(null);
    setSearchResults([]);

    const res = await searchProjectContext(
      selectedProjectId,
      semanticQuery.trim(),
      5,
      0.0,
      useMockDiscovery
    );

    if (res.success && res.data) {
      setSearchResults(res.data.results);
      setSearchDisclaimer(res.data.disclaimer);
    } else {
      setSearchErrorMsg(res.error || "Context retrieval failed.");
    }
    setIsSearchingContext(false);
  };

  const handleDeleteIndex = async () => {
    if (!selectedProjectId) return;
    if (!confirm("Are you sure you want to delete the vector index? Original uploaded files will remain safe.")) return;

    const res = await deleteProjectIndex(selectedProjectId, useMockDiscovery);
    if (res.success && res.data) {
      setIndexingFeedback({
        type: "success",
        message: res.data.message,
      });
      setSearchResults([]);
      await fetchIndexStatus(selectedProjectId, useMockDiscovery);
    } else {
      setIndexingFeedback({
        type: "error",
        message: res.error || "Failed to delete index.",
      });
    }
  };

  const handleApproveCandidate = (candidate: SearchResultItem) => {
    setContextSelections((prev) => ({
      ...prev,
      [candidate.file_id]: {
        file_id: candidate.file_id,
        selected_all_lines: false,
        line_range: {
          start_line: candidate.start_line,
          end_line: candidate.end_line,
        },
      },
    }));
    setContextFeedback({
      type: "success",
      message: `Approved: ${candidate.relative_path} (Lines ${candidate.start_line}–${candidate.end_line}) added to active context scope. Click 'Lock Context' to persist for AI evidence.`,
    });
  };

  const handleInspectCandidate = (candidate: SearchResultItem) => {
    setSelectedFileId(candidate.file_id);
    setRangeStartInput(candidate.start_line);
    setRangeEndInput(candidate.end_line);
    setWorkspaceTab("viewer");
  };

  // Helpers
  const handleSelectAllFiles = () => {
    if (!activeProject?.files) return;
    const map: Record<string, ContextFileSelection> = {};
    for (const f of activeProject.files) {
      map[f.id] = {
        file_id: f.id,
        selected_all_lines: true,
        line_range: null,
      };
    }
    setContextSelections(map);
  };

  const handleDeselectAllFiles = () => {
    setContextSelections({});
  };

  const filteredFiles = useMemo(() => {
    if (!activeProject?.files) return [];
    if (!fileSearchQuery.trim()) return activeProject.files;
    const q = fileSearchQuery.toLowerCase();
    return activeProject.files.filter(
      (f) =>
        f.relative_path.toLowerCase().includes(q) ||
        f.filename.toLowerCase().includes(q) ||
        f.file_type.toLowerCase().includes(q)
    );
  }, [activeProject, fileSearchQuery]);

  const codeLines = useMemo(() => {
    if (!fileContentData?.content) return [];
    return fileContentData.content.split("\n");
  }, [fileContentData]);

  const currentFileContext = selectedFileId ? contextSelections[selectedFileId] : null;

  // Phase 9: Live Assembled Context Statistics & Token Estimation
  const assembledContextStats = useMemo(() => {
    let totalLines = 0;
    let totalChars = 0;
    const items: Array<{
      fileId: string;
      relativePath: string;
      linesScoped: string;
      lineCount: number;
    }> = [];

    if (!activeProject?.files) {
      return { totalFiles: 0, totalLines: 0, totalChars: 0, estimatedTokens: 0, items: [] };
    }

    for (const [fileId, sel] of Object.entries(contextSelections)) {
      const file = activeProject.files.find((f) => f.id === fileId);
      if (!file) continue;

      let fileLines = file.line_count;
      let lineLabel = `Whole File (1–${file.line_count})`;

      if (!sel.selected_all_lines && sel.line_range) {
        const start = Math.max(1, sel.line_range.start_line);
        const end = Math.min(file.line_count, Math.max(start, sel.line_range.end_line));
        fileLines = Math.max(1, end - start + 1);
        lineLabel = `Lines ${start}–${end}`;
      }

      const estChars = fileLines * 45 + 120;
      totalLines += fileLines;
      totalChars += estChars;

      items.push({
        fileId,
        relativePath: file.relative_path,
        linesScoped: lineLabel,
        lineCount: fileLines,
      });
    }

    return {
      totalFiles: items.length,
      totalLines,
      totalChars,
      estimatedTokens: Math.ceil(totalChars / 4),
      items,
    };
  }, [contextSelections, activeProject]);

  const filteredEvalResults = useMemo(() => {
    if (!activeEvalRun?.results) return [];
    if (evalFilterMode === "all") return activeEvalRun.results;
    return activeEvalRun.results.filter((r) => r.mode === evalFilterMode);
  }, [activeEvalRun, evalFilterMode]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Mobile Drawer Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-slate-900/95 backdrop-blur-md transition-transform duration-200 ease-in-out md:static md:translate-x-0 ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-800 px-6">
          <button
            onClick={() => {
              setSelectedProjectId(null);
              setActiveTab("dashboard");
            }}
            className="flex items-center gap-3 text-left focus:outline-none"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white shadow-sm">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <div>
              <span className="font-semibold text-base tracking-tight text-white block">
                ContextControl
              </span>
              <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
                Evidence Engine
              </span>
            </div>
          </button>

          <button
            className="text-slate-400 hover:text-white md:hidden"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1.5 px-3 py-4">
          <button
            onClick={() => {
              setSelectedProjectId(null);
              setActiveTab("dashboard");
              setMobileMenuOpen(false);
            }}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "dashboard" && !selectedProjectId
                ? "bg-indigo-600/15 text-indigo-400 border border-indigo-500/20"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect width="7" height="9" x="3" y="3" rx="1" />
              <rect width="7" height="5" x="14" y="3" rx="1" />
              <rect width="7" height="9" x="14" y="12" rx="1" />
              <rect width="7" height="5" x="3" y="16" rx="1" />
            </svg>
            Dashboard
          </button>

          <button
            onClick={() => {
              setSelectedProjectId(null);
              setActiveTab("projects");
              setMobileMenuOpen(false);
            }}
            className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              (activeTab === "projects" && !selectedProjectId) || selectedProjectId
                ? "bg-indigo-600/15 text-indigo-400 border border-indigo-500/20"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-3">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z" />
              </svg>
              Projects
            </div>
            {projects.length > 0 && (
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                {projects.length}
              </span>
            )}
          </button>

          <button
            onClick={() => {
              setSelectedProjectId(null);
              setActiveTab("evaluation");
              setMobileMenuOpen(false);
            }}
            className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "evaluation"
                ? "bg-indigo-600/15 text-indigo-400 border border-indigo-500/20"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-3">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Evaluation & Reliability
            </div>
            <span className="rounded bg-indigo-500/20 text-indigo-300 px-1.5 py-0.2 text-[10px] font-mono">
              Benchmark
            </span>
          </button>

          <button
            onClick={() => {
              setActiveTab("settings");
              setMobileMenuOpen(false);
            }}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "settings"
                ? "bg-indigo-600/15 text-indigo-400 border border-indigo-500/20"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            Settings
          </button>
        </nav>

        {/* Sidebar Footer */}
        <div className="border-t border-slate-800 p-4">
          <div className="rounded-lg bg-slate-950/60 p-3 border border-slate-800/80">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Benchmark Runs</span>
              <span className="font-mono text-indigo-400 font-medium">
                {evalRuns.length} Recorded
              </span>
            </div>
            <div className="mt-1 text-[11px] text-slate-500 font-mono truncate">
              {API_BASE_URL}
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-900/60 px-4 md:px-8 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="text-slate-400 hover:text-white md:hidden p-1.5 rounded-lg hover:bg-slate-800"
              aria-label="Open navigation menu"
            >
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2 text-sm">
              <span className="capitalize text-slate-300 font-medium">
                {selectedProjectId ? `Projects / ${activeProject?.name}` : activeTab}
              </span>
            </div>
          </div>

          {/* Backend Connection Indicator & Context Quick Save */}
          <div className="flex items-center gap-3">
            {selectedProjectId && (
              <button
                onClick={handleSaveContext}
                disabled={isSavingContext}
                className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/40 bg-indigo-600/20 px-3 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-600/30 transition-colors"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
                {isSavingContext ? "Saving..." : "Lock Context"}
              </button>
            )}

            <div
              className={`flex items-center gap-2.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                status === "connected"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : status === "disconnected"
                  ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-300"
              }`}
            >
              <span
                className={`relative flex h-2 w-2 rounded-full ${
                  status === "connected"
                    ? "bg-emerald-400"
                    : status === "disconnected"
                    ? "bg-rose-400"
                    : "bg-amber-400"
                }`}
              >
                {status === "connected" && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                )}
              </span>
              <span>{status === "connected" ? "Backend Connected" : "Disconnected"}</span>
            </div>
          </div>
        </header>

        {/* Feedback Alert Banner */}
        {contextFeedback && (
          <div
            className={`border-b px-4 py-2 text-xs flex items-center justify-between ${
              contextFeedback.type === "success"
                ? "bg-emerald-950/70 border-emerald-800 text-emerald-200"
                : "bg-rose-950/70 border-rose-800 text-rose-200"
            }`}
          >
            <span>{contextFeedback.message}</span>
            <button
              onClick={() => setContextFeedback(null)}
              className="text-slate-400 hover:text-white ml-3 text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* Scrollable Main Area */}
        <main className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
          <div className="mx-auto max-w-7xl space-y-6">
            {/* VIEW 1: EVALUATION DASHBOARD */}
            {activeTab === "evaluation" && !selectedProjectId ? (
              <div className="space-y-6">
                {/* Header */}
                <div className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-900/60 p-6 shadow-sm">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                    <div className="space-y-2 max-w-3xl">
                      <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
                        Empirical Reliability Evaluation
                      </div>
                      <h2 className="text-2xl font-bold tracking-tight text-white">
                        Evaluation & Reliability Benchmark
                      </h2>
                      <p className="text-xs md:text-sm text-slate-400 leading-relaxed">
                        Compare Baseline LLM prompting against ContextControl&apos;s Context Lock across citation validity, evidence coverage, unsupported claims, and insufficient-context handling using standardized fixture codebases.
                      </p>
                    </div>

                    {/* Run Trigger Card */}
                    <div className="shrink-0 flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 p-4 min-w-[280px]">
                      <span className="text-xs font-medium text-slate-300 font-mono uppercase tracking-wider">
                        Run New Benchmark
                      </span>

                      {/* Mock mode toggle */}
                      <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={useMockEval}
                          onChange={(e) => setUseMockEval(e.target.checked)}
                          className="h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0 cursor-pointer"
                        />
                        <span>Deterministic Mock Mode (Free & Fast)</span>
                      </label>

                      {evalError && (
                        <div className="text-[11px] text-rose-400">{evalError}</div>
                      )}

                      <button
                        onClick={handleRunEvaluation}
                        disabled={isRunningEval}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 shadow-sm"
                      >
                        {isRunningEval ? (
                          <>
                            <svg className="h-4 w-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                            </svg>
                            Running Benchmark...
                          </>
                        ) : (
                          <>
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            Run Evaluation Suite
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Benchmark Comparison Across Modes */}
                {activeEvalRun ? (
                  <div className="space-y-6">
                    {/* Run Header & Historical Runs Selector */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                      <div>
                        <h3 className="text-base font-semibold text-white flex items-center gap-2">
                          <span>Evaluation Run:</span>
                          <span className="font-mono text-xs text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                            {activeEvalRun.id.slice(0, 8)}...
                          </span>
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Dataset: {activeEvalRun.dataset_id} • Model: {activeEvalRun.model_name} • Total Cases: {activeEvalRun.total_cases}
                        </p>
                      </div>

                      {/* Run selector */}
                      {evalRuns.length > 1 && (
                        <select
                          value={activeEvalRun.id}
                          onChange={(e) => handleSelectRun(e.target.value)}
                          className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
                        >
                          {evalRuns.map((r) => (
                            <option key={r.id} value={r.id}>
                              Run {r.id.slice(0, 8)} ({new Date(r.created_at).toLocaleTimeString()})
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Mode Comparison Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {activeEvalRun.comparison.map((c) => {
                        const isBaseline = c.mode === "baseline";
                        const isCitations = c.mode === "context_lock_citations";

                        return (
                          <div
                            key={c.mode}
                            className={`rounded-2xl border p-5 flex flex-col justify-between ${
                              isCitations
                                ? "border-indigo-500/40 bg-indigo-950/20"
                                : isBaseline
                                ? "border-slate-800 bg-slate-900/40"
                                : "border-slate-800 bg-slate-900/60"
                            }`}
                          >
                            <div>
                              <div className="flex items-center justify-between mb-3">
                                <span className="font-mono text-xs uppercase tracking-wider font-semibold text-white">
                                  {c.mode === "baseline"
                                    ? "Mode A: Baseline"
                                    : c.mode === "context_lock"
                                    ? "Mode B: Context Lock"
                                    : "Mode C: Lock + Citations"}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">
                                  {c.total_cases} cases
                                </span>
                              </div>

                              <div className="space-y-2.5 text-xs">
                                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                                  <span className="text-slate-400">Citation Validity:</span>
                                  <span className="font-mono font-semibold">
                                    {c.citation_validity_rate !== null ? (
                                      <span className="text-emerald-400">
                                        {(c.citation_validity_rate * 100).toFixed(0)}%
                                      </span>
                                    ) : (
                                      <span className="text-slate-500">N/A (Unconstrained)</span>
                                    )}
                                  </span>
                                </div>

                                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                                  <span className="text-slate-400">Unsupported Claims:</span>
                                  <span className="font-mono font-semibold">
                                    <span
                                      className={
                                        c.unsupported_claim_rate === 0
                                          ? "text-emerald-400"
                                          : "text-amber-400"
                                      }
                                    >
                                      {(c.unsupported_claim_rate * 100).toFixed(0)}%
                                    </span>
                                  </span>
                                </div>

                                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                                  <span className="text-slate-400">Insufficient-Context Handling:</span>
                                  <span className="font-mono font-semibold text-indigo-300">
                                    {(c.insufficient_context_accuracy * 100).toFixed(0)}%
                                  </span>
                                </div>

                                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                                  <span className="text-slate-400">Avg Tokens:</span>
                                  <span className="font-mono text-slate-300">{c.avg_tokens} tok</span>
                                </div>

                                <div className="flex justify-between items-center py-1">
                                  <span className="text-slate-400">Avg Latency:</span>
                                  <span className="font-mono text-slate-300">{c.avg_latency_ms} ms</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Detailed Per-Question Results Table */}
                    <div className="space-y-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <h4 className="text-sm font-semibold text-white">
                          Per-Question Breakdown & Citations Audit
                        </h4>

                        <div className="flex items-center gap-1.5 text-xs">
                          <span className="text-slate-400">Filter Mode:</span>
                          <select
                            value={evalFilterMode}
                            onChange={(e) => setEvalFilterMode(e.target.value)}
                            className="rounded-lg border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none"
                          >
                            <option value="all">All Modes ({activeEvalRun.results.length})</option>
                            <option value="baseline">Mode A: Baseline</option>
                            <option value="context_lock">Mode B: Context Lock</option>
                            <option value="context_lock_citations">Mode C: Lock + Citations</option>
                          </select>
                        </div>
                      </div>

                      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/30">
                        <table className="w-full text-left text-xs text-slate-300">
                          <thead className="bg-slate-900/80 text-[11px] uppercase tracking-wider font-mono text-slate-400 border-b border-slate-800">
                            <tr>
                              <th className="px-4 py-3">Mode</th>
                              <th className="px-4 py-3">Question</th>
                              <th className="px-4 py-3">Answer & Output</th>
                              <th className="px-4 py-3">Citations Status</th>
                              <th className="px-4 py-3">Latency</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 font-sans">
                            {filteredEvalResults.map((item) => (
                              <tr key={item.id} className="hover:bg-slate-800/20 transition-colors">
                                <td className="px-4 py-3 align-top whitespace-nowrap">
                                  <span
                                    className={`rounded px-2 py-0.5 text-[10px] font-mono uppercase font-semibold ${
                                      item.mode === "context_lock_citations"
                                        ? "bg-indigo-500/20 text-indigo-300"
                                        : item.mode === "context_lock"
                                        ? "bg-emerald-500/20 text-emerald-300"
                                        : "bg-slate-800 text-slate-400"
                                    }`}
                                  >
                                    {item.mode}
                                  </span>
                                </td>

                                <td className="px-4 py-3 align-top max-w-xs">
                                  <div className="font-medium text-slate-100">{item.question}</div>
                                  <div className="text-[11px] text-slate-500 mt-1 font-mono">
                                    Ref: {item.reference_answer}
                                  </div>
                                </td>

                                <td className="px-4 py-3 align-top max-w-sm">
                                  <div className="text-slate-200 leading-relaxed line-clamp-3">
                                    {item.model_answer}
                                  </div>
                                  <div className="text-[10px] text-slate-400 mt-1 font-mono">
                                    Correctness: {(item.answer_correctness * 100).toFixed(0)}% • Tokens: {item.tokens_used}
                                  </div>
                                </td>

                                <td className="px-4 py-3 align-top whitespace-nowrap font-mono text-[11px]">
                                  {item.citations.length > 0 ? (
                                    <div className="space-y-1">
                                      <span className="text-emerald-400 font-semibold block">
                                        {item.citations.filter((c) => c.verified).length}/{item.citations.length} Verified
                                      </span>
                                      {item.citations.map((c, idx) => (
                                        <div key={idx} className="text-[10px] text-slate-400 truncate max-w-[180px]">
                                          {c.file_path}:L{c.start_line}–{c.end_line}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-slate-500">
                                      {item.mode === "baseline" ? "No Citations (Baseline)" : "0 Citations"}
                                    </span>
                                  )}
                                </td>

                                <td className="px-4 py-3 align-top font-mono text-[11px] text-slate-400 whitespace-nowrap">
                                  {item.latency_ms} ms
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Empty state */
                  <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 px-6 py-20 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800/80 text-slate-400 mb-4 border border-slate-700/50">
                      <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                    </div>
                    <h4 className="text-base font-medium text-slate-200">No evaluation runs yet</h4>
                    <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-slate-400">
                      Run the standardized benchmark to compare Baseline prompting with ContextControl Context Lock on citation validity, token consumption, and evidence coverage.
                    </p>
                    <div className="mt-6">
                      <button
                        onClick={handleRunEvaluation}
                        disabled={isRunningEval}
                        className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors"
                      >
                        Run Benchmark (Mock Mode)
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : selectedProjectId ? (
              activeProject ? (
                /* VIEW 2: PROJECT WORKSPACE VIEW */
                <div className="space-y-6">
                {/* Workspace Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
                  <div>
                    <div className="flex items-center gap-3 mb-2">
                      <button
                        onClick={() => setSelectedProjectId(null)}
                        className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                        </svg>
                        Back to All Projects
                      </button>
                      <span className="text-slate-600 text-xs">•</span>
                      <button
                        onClick={async () => {
                          if (
                            confirm(
                              `Are you sure you want to delete project '${activeProject.name}'? All files, context selections, and index chunks will be permanently removed.`
                            )
                          ) {
                            const res = await deleteProject(activeProject.id);
                            if (res.success) {
                              setSelectedProjectId(null);
                              setActiveProject(null);
                              await fetchProjects();
                            } else {
                              alert(res.error || "Failed to delete project");
                            }
                          }
                        }}
                        className="text-xs text-rose-400/80 hover:text-rose-300 transition-colors"
                      >
                        Delete Workspace
                      </button>
                    </div>
                    <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
                      {activeProject.name}
                    </h2>
                    <p className="text-xs text-slate-400 mt-1">
                      Evidence Workspace • {activeProject.file_count} Files Indexed •{" "}
                      <span className="text-indigo-400 font-semibold">
                        {Object.keys(contextSelections).length} in Active Context Lock
                      </span>
                    </p>
                  </div>

                  {/* Workspace Tabs */}
                  <div className="flex items-center gap-2 bg-slate-900 p-1 rounded-xl border border-slate-800">
                    <button
                      onClick={() => setWorkspaceTab("viewer")}
                      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                        workspaceTab === "viewer"
                          ? "bg-indigo-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                      </svg>
                      Files & Line Scope
                    </button>

                    <button
                      onClick={() => {
                        setWorkspaceTab("discovery");
                        if (selectedProjectId) {
                          fetchIndexStatus(selectedProjectId, useMockDiscovery);
                        }
                      }}
                      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                        workspaceTab === "discovery"
                          ? "bg-indigo-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                      Find Relevant Context
                      {indexStatus?.configured && indexStatus.total_chunks > 0 && (
                        <span className="rounded-full bg-emerald-400/20 px-1.5 py-0.2 text-[10px] text-emerald-300">
                          {indexStatus.total_chunks}
                        </span>
                      )}
                    </button>

                    <button
                      onClick={() => setWorkspaceTab("chat")}
                      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                        workspaceTab === "chat"
                          ? "bg-indigo-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                      Context-Locked Chat
                      {Object.keys(contextSelections).length > 0 && (
                        <span className="rounded-full bg-indigo-400/20 px-1.5 py-0.2 text-[10px] text-indigo-300">
                          {Object.keys(contextSelections).length}
                        </span>
                      )}
                    </button>
                  </div>
                </div>

                {/* Workspace Viewer Tab */}
                {workspaceTab === "viewer" && (
                  <div className="space-y-6">
                    {/* Upload */}
                    <section className="rounded-2xl border border-slate-800 bg-slate-900/30 p-4">
                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                        <div>
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                            Add Source Files or Codebase ZIP
                          </h4>
                          <p className="text-[11px] text-slate-400">
                            Safely inspects text source files. Excludes binaries and secrets.
                          </p>
                        </div>

                        <form onSubmit={handleFileUpload} className="flex items-center gap-2">
                          <input
                            id="file-upload-input"
                            type="file"
                            multiple
                            onChange={(e) => setSelectedUploadFiles(e.target.files)}
                            className="text-xs text-slate-400 file:mr-2 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
                          />
                          <button
                            type="submit"
                            disabled={isUploading || !selectedUploadFiles || selectedUploadFiles.length === 0}
                            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                          >
                            {isUploading ? "Uploading..." : "Upload"}
                          </button>
                        </form>
                      </div>

                      {uploadSuccessMsg && (
                        <div className="mt-2 text-xs text-emerald-400">{uploadSuccessMsg}</div>
                      )}
                      {uploadErrorMsg && (
                        <div className="mt-2 text-xs text-rose-400">{uploadErrorMsg}</div>
                      )}
                    </section>

                    {/* Two-Pane File Browser & Code Viewer */}
                    <section className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[620px] rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
                      {/* Left Pane (4 cols) */}
                      <div className="lg:col-span-4 flex flex-col border-b lg:border-b-0 lg:border-r border-slate-800 h-full overflow-hidden">
                        <div className="p-3 border-b border-slate-800/80 bg-slate-900/60 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-white">Files ({activeProject.files?.length || 0})</span>
                            <span className="text-[10px] rounded bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 font-mono">
                              {Object.keys(contextSelections).length} selected
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 text-[11px]">
                            <button
                              onClick={handleSelectAllFiles}
                              className="text-slate-400 hover:text-indigo-400 transition-colors"
                            >
                              All
                            </button>
                            <span className="text-slate-600">•</span>
                            <button
                              onClick={handleDeselectAllFiles}
                              className="text-slate-400 hover:text-rose-400 transition-colors"
                            >
                              None
                            </button>
                          </div>
                        </div>

                        <div className="p-2.5 border-b border-slate-800/60 bg-slate-950/40">
                          <input
                            type="text"
                            placeholder="Search files..."
                            value={fileSearchQuery}
                            onChange={(e) => setFileSearchQuery(e.target.value)}
                            className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                          />
                        </div>

                        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/40">
                          {filteredFiles.length > 0 ? (
                            filteredFiles.map((file) => {
                              const isSelectedForContext = !!contextSelections[file.id];
                              const isCurrentlyViewing = selectedFileId === file.id;
                              const selInfo = contextSelections[file.id];
                              const isCustomLines = selInfo && !selInfo.selected_all_lines && selInfo.line_range;

                              return (
                                <div
                                  key={file.id}
                                  className={`flex items-center justify-between px-3 py-2.5 text-xs cursor-pointer transition-colors ${
                                    isCurrentlyViewing
                                      ? "bg-slate-800/80 border-l-2 border-indigo-500"
                                      : "hover:bg-slate-800/30"
                                  }`}
                                  onClick={() => setSelectedFileId(file.id)}
                                >
                                  <div className="flex items-center gap-2.5 min-w-0">
                                    <input
                                      type="checkbox"
                                      checked={isSelectedForContext}
                                      onChange={(e) => {
                                        e.stopPropagation();
                                        handleToggleFileSelection(file.id);
                                      }}
                                      className="h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                                    />
                                    <div className="min-w-0">
                                      <span
                                        className={`font-mono text-xs block truncate ${
                                          isCurrentlyViewing ? "text-white font-medium" : "text-slate-300"
                                        }`}
                                      >
                                        {file.relative_path}
                                      </span>
                                      <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono mt-0.5">
                                        <span>{file.line_count} lines</span>
                                        <span>•</span>
                                        <span>{formatBytes(file.size_bytes)}</span>
                                      </div>
                                    </div>
                                  </div>

                                  <div className="flex items-center gap-1 shrink-0 ml-2">
                                    {isCustomLines && (
                                      <span className="rounded bg-amber-500/15 text-amber-300 px-1.5 py-0.5 text-[9px] font-mono">
                                        L{selInfo.line_range?.start_line}–{selInfo.line_range?.end_line}
                                      </span>
                                    )}
                                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400 uppercase">
                                      {file.file_type}
                                    </span>
                                  </div>
                                </div>
                              );
                            })
                          ) : (
                            <div className="p-8 text-center text-xs text-slate-500">
                              {activeProject.files && activeProject.files.length > 0
                                ? "No matching files."
                                : "No files uploaded yet."}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right Pane (8 cols) */}
                      <div className="lg:col-span-8 flex flex-col h-full overflow-hidden bg-slate-950/60">
                        <div className="p-3 border-b border-slate-800/80 bg-slate-900/60 flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-xs font-semibold text-white truncate">
                              {fileContentData ? fileContentData.relative_path : "Select a file to inspect"}
                            </span>
                          </div>

                          {fileContentData && selectedFileId && (
                            <div className="flex items-center gap-2">
                              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={!currentFileContext?.selected_all_lines}
                                  onChange={(e) => handleToggleAllLinesForCurrentFile(!e.target.checked)}
                                  className="h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0 cursor-pointer"
                                />
                                <span>Scope Custom Lines</span>
                              </label>

                              {!currentFileContext?.selected_all_lines && (
                                <div className="flex items-center gap-1.5 bg-slate-900 px-2 py-1 rounded-lg border border-slate-800">
                                  <span className="text-[10px] text-slate-400">L:</span>
                                  <input
                                    type="number"
                                    min={1}
                                    max={fileContentData.line_count}
                                    value={rangeStartInput}
                                    onChange={(e) => setRangeStartInput(parseInt(e.target.value) || 1)}
                                    className="w-12 bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-xs text-center text-slate-100 font-mono"
                                  />
                                  <span className="text-slate-500 text-xs">–</span>
                                  <input
                                    type="number"
                                    min={rangeStartInput}
                                    max={fileContentData.line_count}
                                    value={rangeEndInput}
                                    onChange={(e) => setRangeEndInput(parseInt(e.target.value) || fileContentData.line_count)}
                                    className="w-12 bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-xs text-center text-slate-100 font-mono"
                                  />
                                  <button
                                    onClick={handleApplyLineRange}
                                    className="rounded bg-indigo-600/80 hover:bg-indigo-600 text-white px-2 py-0.5 text-[10px] font-medium"
                                  >
                                    Apply
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        <div className="flex-1 overflow-auto font-mono text-xs select-text">
                          {loadingFileContent ? (
                            <div className="flex items-center justify-center h-full text-slate-500 text-xs">
                              Loading file content...
                            </div>
                          ) : fileContentError ? (
                            <div className="flex items-center justify-center h-full text-rose-400 text-xs">
                              {fileContentError}
                            </div>
                          ) : fileContentData ? (
                            <div className="min-w-full inline-block py-2">
                              {codeLines.map((line, idx) => {
                                const lineNum = idx + 1;
                                const isWithinRange =
                                  currentFileContext &&
                                  !currentFileContext.selected_all_lines &&
                                  currentFileContext.line_range &&
                                  lineNum >= currentFileContext.line_range.start_line &&
                                  lineNum <= currentFileContext.line_range.end_line;

                                return (
                                  <div
                                    key={idx}
                                    className={`flex hover:bg-slate-800/40 transition-colors leading-relaxed ${
                                      isWithinRange
                                        ? "bg-indigo-600/15 border-l-2 border-indigo-400"
                                        : ""
                                    }`}
                                  >
                                    <span className="w-12 shrink-0 select-none text-right pr-4 text-slate-600 text-[11px] font-mono">
                                      {lineNum}
                                    </span>
                                    <span className="flex-1 whitespace-pre pr-4 text-slate-200">
                                      {line}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="flex flex-col items-center justify-center h-full text-slate-500 text-xs gap-2">
                              <span>Select a file from the list to view its code and scope line ranges.</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </section>

                    {/* Phase 9: Persistent Context Scope & Lock Bar */}
                    <div className="rounded-2xl border border-indigo-500/30 bg-slate-900/80 p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400">
                          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                          </svg>
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-xs font-semibold text-white uppercase tracking-wider">
                              Context Lock Scope
                            </h4>
                            <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-mono text-indigo-300">
                              {assembledContextStats.totalFiles} files • {assembledContextStats.totalLines} lines
                            </span>
                            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-400 border border-slate-700">
                              ~{assembledContextStats.estimatedTokens} tokens
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {savedContext
                              ? `Locked Evidence: ${savedContext.total_selected_files} files, ${savedContext.total_selected_lines} lines ready for AI verification.`
                              : "Review selected files and click 'Lock Context' to enforce AI evidence boundaries."}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setShowContextPreviewModal(true)}
                          disabled={assembledContextStats.totalFiles === 0}
                          className="rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50 transition-colors"
                        >
                          Inspect Exact Context
                        </button>

                        <button
                          type="button"
                          onClick={handleSaveContext}
                          disabled={isSavingContext || assembledContextStats.totalFiles === 0}
                          className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors shadow-sm"
                        >
                          {isSavingContext ? "Locking..." : "Lock Context"}
                        </button>

                        {assembledContextStats.totalFiles > 0 && (
                          <button
                            type="button"
                            onClick={handleClearContext}
                            className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-400 hover:text-rose-400 transition-colors"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    </div>

                    {contextFeedback && (
                      <div
                        className={`rounded-xl p-3 text-xs ${
                          contextFeedback.type === "success"
                            ? "bg-emerald-950/40 border border-emerald-500/30 text-emerald-300"
                            : "bg-rose-950/40 border border-rose-500/30 text-rose-300"
                        }`}
                      >
                        {contextFeedback.message}
                      </div>
                    )}
                  </div>
                )}

                {/* Workspace Context Discovery Tab (Phase 7) */}
                {workspaceTab === "discovery" && (
                  <div className="space-y-6">
                    {/* Indexing Status & Configuration Card */}
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/60">
                        <div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`h-2.5 w-2.5 rounded-full ${
                                indexStatus?.configured
                                  ? "bg-emerald-400"
                                  : "bg-amber-400"
                              }`}
                            />
                            <h3 className="text-sm font-semibold text-white">
                              Codebase Vector Indexing
                            </h3>
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-300">
                              {indexStatus?.is_mock
                                ? "Mock Vector Store"
                                : indexStatus?.pgvector_enabled
                                ? "pgvector (Active)"
                                : "pgvector (Unconfigured)"}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-1">
                            Model:{" "}
                            <span className="font-mono text-indigo-400">
                              {indexStatus?.embedding_model || "text-embedding-004"}
                            </span>{" "}
                            ({indexStatus?.embedding_dimension || 768}-dim) •{" "}
                            {indexStatus?.total_chunks || 0} chunks across{" "}
                            {indexStatus?.total_indexed_files || 0} files.
                          </p>
                        </div>

                        {/* Index Controls */}
                        <div className="flex flex-wrap items-center gap-2">
                          <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer mr-2">
                            <input
                              type="checkbox"
                              checked={useMockDiscovery}
                              onChange={(e) => {
                                setUseMockDiscovery(e.target.checked);
                                if (selectedProjectId) {
                                  fetchIndexStatus(selectedProjectId, e.target.checked);
                                }
                              }}
                              className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-0"
                            />
                            <span>Mock Mode (Offline)</span>
                          </label>

                          <button
                            type="button"
                            onClick={() => handleIndexCodebase(false)}
                            disabled={isIndexingCodebase}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors shadow-sm"
                          >
                            {isIndexingCodebase ? "Indexing..." : "Index Codebase"}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleIndexCodebase(true)}
                            disabled={isIndexingCodebase}
                            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-50 transition-colors"
                          >
                            Force Re-Index
                          </button>

                          {indexStatus && indexStatus.total_chunks > 0 && (
                            <button
                              type="button"
                              onClick={handleDeleteIndex}
                              className="inline-flex items-center gap-1.5 rounded-xl border border-rose-900/50 bg-rose-950/20 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-950/40 transition-colors"
                            >
                              Clear Index
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Setup Guidance Banner when pgvector is not configured */}
                      {!indexStatus?.configured && !useMockDiscovery && (
                        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-950/20 p-3.5 text-xs text-amber-200">
                          <div className="flex items-start gap-2.5">
                            <svg className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <div className="space-y-1">
                              <p className="font-semibold text-amber-300">
                                PostgreSQL with pgvector is not yet configured.
                              </p>
                              <p className="text-amber-200/80 text-[11px] leading-relaxed">
                                To enable production semantic vector search, set <code className="bg-amber-950/80 px-1 py-0.5 rounded text-amber-100 font-mono">DATABASE_URL</code> in <code className="bg-amber-950/80 px-1 py-0.5 rounded text-amber-100 font-mono">backend/.env</code> pointing to PostgreSQL with the <code className="bg-amber-950/80 px-1 py-0.5 rounded text-amber-100 font-mono">vector</code> extension.
                                You can check <strong>Mock Mode (Offline)</strong> above to test chunking and ranking immediately without PostgreSQL.
                              </p>
                              <p className="text-[11px] text-slate-400 pt-1">
                                Note: Manual file browsing, Context Lock, and citation validation remain 100% operational.
                              </p>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Feedback banner */}
                      {indexingFeedback && (
                        <div
                          className={`mt-4 rounded-xl p-3 text-xs ${
                            indexingFeedback.type === "success"
                              ? "bg-emerald-950/40 border border-emerald-500/30 text-emerald-300"
                              : "bg-rose-950/40 border border-rose-500/30 text-rose-300"
                          }`}
                        >
                          {indexingFeedback.message}
                        </div>
                      )}
                    </div>

                    {/* Semantic Search Query Form */}
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/30 p-5">
                      <div className="mb-3">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                          Semantic Context Search
                        </h4>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Describe the feature, logic, or behavior you are looking for. Semantic search suggests relevant code snippets.
                        </p>
                      </div>

                      <form onSubmit={handleSearchContext} className="flex gap-2">
                        <input
                          type="text"
                          value={semanticQuery}
                          onChange={(e) => setSemanticQuery(e.target.value)}
                          placeholder="e.g. 'JWT token expiration check', 'bcrypt password verification', 'database pool configuration'..."
                          className="flex-1 rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                        />
                        <button
                          type="submit"
                          disabled={isSearchingContext || !semanticQuery.trim()}
                          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors shadow-sm"
                        >
                          {isSearchingContext ? "Searching..." : "Find Relevant Code"}
                        </button>
                      </form>

                      {searchErrorMsg && (
                        <div className="mt-3 rounded-xl border border-rose-500/30 bg-rose-950/30 p-3 text-xs text-rose-300">
                          {searchErrorMsg}
                        </div>
                      )}
                    </div>

                    {/* 3-Tier Context Hierarchy Notice */}
                    <div className="rounded-2xl border border-indigo-500/20 bg-indigo-950/10 p-4">
                      <div className="flex items-start gap-3">
                        <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shrink-0">
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                          </svg>
                        </div>
                        <div className="space-y-1 text-xs text-slate-300">
                          <p className="font-semibold text-white">
                            Developer Control Guarantee (Context Lock)
                          </p>
                          <p className="text-slate-400 leading-relaxed text-[11px]">
                            • <span className="text-amber-400 font-semibold">Suggested Context:</span> Vector search candidates below are suggestions only.<br />
                            • <span className="text-emerald-400 font-semibold">Selected Context:</span> You must explicitly click <strong className="text-white">Approve & Add</strong> for code to be considered.<br />
                            • <span className="text-indigo-400 font-semibold">Locked Context:</span> The backend independently reconstructs selected lines from disk and validates ground-truth citations.
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Search Results Candidates List */}
                    {searchResults.length > 0 && (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                            <span>Candidate Snippets Surfaced</span>
                            <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-mono text-indigo-300">
                              {searchResults.length} results
                            </span>
                          </h4>
                          <span className="text-[11px] text-slate-500 italic">
                            Ranked by vector cosine similarity
                          </span>
                        </div>

                        <div className="space-y-3">
                          {searchResults.map((item) => {
                            const isAlreadySelected = !!contextSelections[item.file_id];

                            return (
                              <div
                                key={item.chunk_id}
                                className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 space-y-3 hover:border-slate-700 transition-colors"
                              >
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-mono text-xs font-bold text-white">
                                      {item.relative_path}
                                    </span>
                                    <span className="rounded-md bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-indigo-300 border border-slate-700">
                                      Lines {item.start_line}–{item.end_line}
                                    </span>
                                    <span className="rounded-md bg-amber-500/10 px-2 py-0.5 text-[10px] font-mono text-amber-300 border border-amber-500/20">
                                      Similarity: {item.similarity_score}
                                    </span>
                                    <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                                      Suggested Context
                                    </span>
                                  </div>

                                  <div className="flex items-center gap-2 shrink-0">
                                    <button
                                      type="button"
                                      onClick={() => handleInspectCandidate(item)}
                                      className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
                                    >
                                      Inspect in Viewer
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => handleApproveCandidate(item)}
                                      className={`rounded-lg px-3 py-1 text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                                        isAlreadySelected
                                          ? "bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-600/50"
                                          : "bg-emerald-600 text-white hover:bg-emerald-500 shadow-sm"
                                      }`}
                                    >
                                      {isAlreadySelected ? "✓ In Selected Scope" : "+ Approve & Add"}
                                    </button>
                                  </div>
                                </div>

                                {/* Preview block */}
                                <div className="rounded-xl border border-slate-950 bg-slate-950/80 p-3 font-mono text-xs text-slate-300 overflow-x-auto">
                                  <pre className="whitespace-pre">{item.preview}</pre>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {searchDisclaimer && (
                          <p className="text-[11px] text-slate-500 italic">
                            * {searchDisclaimer}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Workspace Chat Tab */}
                {workspaceTab === "chat" && (
                  <div className="space-y-6">
                    <div className="rounded-2xl border border-indigo-500/30 bg-indigo-950/20 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
                            Context Lock Active
                          </h4>
                        </div>
                        <p className="text-xs text-slate-300 mt-1">
                          Gemini will reason <strong>strictly</strong> using the {Object.keys(contextSelections).length} scoped files. Unprovided code or files will not be assumed.
                        </p>
                      </div>

                      <button
                        onClick={() => setWorkspaceTab("viewer")}
                        className="rounded-lg border border-indigo-500/30 bg-indigo-900/40 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-900/70 transition-colors shrink-0"
                      >
                        Adjust Selected Files &rarr;
                      </button>
                    </div>

                    {chatError && (
                      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300">
                        <div className="font-semibold text-rose-200 mb-1">AI Request Notice</div>
                        <p>{chatError}</p>
                      </div>
                    )}

                    <form onSubmit={handleAskQuestion} className="space-y-3">
                      <div className="relative rounded-2xl border border-slate-800 bg-slate-900/60 p-3 focus-within:border-indigo-500">
                        <textarea
                          rows={3}
                          value={questionInput}
                          onChange={(e) => setQuestionInput(e.target.value)}
                          placeholder="Ask a question about the scoped code evidence..."
                          className="w-full bg-transparent text-xs text-slate-100 placeholder-slate-500 focus:outline-none resize-none font-sans"
                          disabled={isAskingQuestion}
                        />
                        <div className="flex items-center justify-between border-t border-slate-800/80 pt-2.5 mt-2">
                          <span className="text-[11px] text-slate-500">
                            Evidence constraint: {Object.keys(contextSelections).length} files locked
                          </span>
                          <button
                            type="submit"
                            disabled={isAskingQuestion || !questionInput.trim() || Object.keys(contextSelections).length === 0}
                            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
                          >
                            {isAskingQuestion ? "Reasoning..." : "Ask Gemini"}
                          </button>
                        </div>
                      </div>
                    </form>

                    <div className="space-y-6">
                      {chatHistory.map((item, index) => (
                        <div key={index} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
                          <div className="flex items-start justify-between gap-4 border-b border-slate-800/80 pb-3">
                            <span className="text-sm font-semibold text-white">{item.question}</span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              {item.model_used} • {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>

                          {item.insufficient_context && (
                            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 space-y-1">
                              <div className="font-semibold text-amber-300">Insufficient Context Acknowledged</div>
                              <p className="text-[11px] text-amber-300/90">
                                The model determined that the currently locked evidence is insufficient to answer without assumptions.
                              </p>
                              {item.missing_context.length > 0 && (
                                <div className="pt-1 text-[11px]">
                                  <strong>Missing Evidence:</strong> {item.missing_context.join(", ")}
                                </div>
                              )}
                            </div>
                          )}

                          <div className="text-xs leading-relaxed text-slate-200 whitespace-pre-wrap">
                            {item.answer}
                          </div>

                          {item.citations && item.citations.length > 0 && (
                            <div className="border-t border-slate-800/80 pt-4 space-y-2">
                              <span className="text-[11px] uppercase font-mono tracking-wider text-slate-400 block">
                                Citations ({item.citations.length})
                              </span>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                                {item.citations.map((c, cIdx) => (
                                  <div
                                    key={cIdx}
                                    onClick={() => handleJumpToCitation(c)}
                                    className={`rounded-xl border p-3 cursor-pointer transition-all ${
                                      c.verified
                                        ? "border-emerald-500/30 bg-emerald-950/20 hover:border-emerald-500/60"
                                        : "border-amber-500/30 bg-amber-950/20 hover:border-amber-500/60"
                                    }`}
                                  >
                                    <div className="flex items-center justify-between text-xs mb-1">
                                      <span className="font-mono font-semibold text-white">
                                        {c.file_path}:L{c.start_line}–L{c.end_line}
                                      </span>
                                      <span
                                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                                          c.verified
                                            ? "bg-emerald-500/20 text-emerald-300"
                                            : "bg-amber-500/20 text-amber-300"
                                        }`}
                                      >
                                        {c.verified ? "Verified" : "Out of Scope"}
                                      </span>
                                    </div>
                                    <p className="text-[11px] text-slate-300 line-clamp-2">{c.claim}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                </div>
              ) : (
                /* SKELETON / TRANSITION VIEW WHILE ACTIVE PROJECT LOADS */
                <div className="flex flex-col items-center justify-center min-h-[450px] rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
                  <div className="h-8 w-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4" />
                  <h3 className="text-sm font-semibold text-slate-200">Opening Project Workspace...</h3>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm">
                    Reconstructing file tree, code viewer, and context lock boundaries.
                  </p>
                </div>
              )
            ) : (
              /* VIEW 3: MAIN DASHBOARD & PROJECTS OVERVIEW */
              <div className="space-y-8">
                <section className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-900/60 p-6 md:p-8 shadow-sm">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                    <div className="space-y-3 max-w-2xl">
                      <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
                        Verified Evidence Engine • Reliability Evaluator
                      </div>
                      <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
                        Control the Context. Improve the Answer.
                      </h2>
                      <p className="text-sm md:text-base leading-relaxed text-slate-400">
                        ContextControl empowers developers to manually select the exact code files and documentation that an AI is permitted to use. Compare Baseline vs Context Lock on the Reliability Dashboard to measure hallucination reduction and citation accuracy.
                      </p>
                    </div>

                    <div className="shrink-0 flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-950/70 p-4 min-w-[200px]">
                      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider font-mono">
                        Workspace Overview
                      </span>
                      <div className="mt-1 flex items-baseline gap-2">
                        <span className="text-2xl font-bold text-white">{projects.length}</span>
                        <span className="text-xs text-slate-400">Projects Managed</span>
                      </div>
                      <span className="text-[11px] text-slate-500 font-mono mt-0.5">
                        Benchmark: {evalRuns.length} Runs
                      </span>
                    </div>
                  </div>
                </section>

                {/* Projects Section */}
                <section className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-white">Project Workspaces</h3>
                      <p className="text-xs text-slate-400">
                        Open a workspace to browse code, view files, and query Gemini with locked evidence.
                      </p>
                    </div>

                    <button
                      onClick={() => {
                        setCreateError(null);
                        setShowCreateModal(true);
                      }}
                      className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-sm"
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                      </svg>
                      Create Project
                    </button>
                  </div>

                  {loadingProjects ? (
                    <div className="py-12 text-center text-xs text-slate-400">
                      Loading projects from storage...
                    </div>
                  ) : projects.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {projects.map((p) => (
                        <div
                          key={p.id}
                          className="group rounded-2xl border border-slate-800 bg-slate-900/40 p-5 hover:border-slate-700 hover:bg-slate-900/70 transition-all flex flex-col justify-between"
                        >
                          <div>
                            <div className="flex items-start justify-between gap-2 mb-3">
                              <h4 className="text-base font-semibold text-white group-hover:text-indigo-300 transition-colors">
                                {p.name}
                              </h4>
                              <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-[10px] font-mono text-slate-400">
                                {p.file_count} files
                              </span>
                            </div>
                            <p className="text-xs text-slate-400 line-clamp-2">
                              Created on {new Date(p.created_at).toLocaleDateString()}
                            </p>
                          </div>

                          <div className="mt-5 pt-4 border-t border-slate-800/80 flex items-center justify-between">
                            <span className="text-xs font-mono text-slate-500">
                              {formatBytes(p.total_size_bytes)}
                            </span>
                            <button
                              onClick={() => {
                                setActiveProject(p);
                                setSelectedProjectId(p.id);
                              }}
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                              Open Workspace & Chat
                              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 px-6 py-16 text-center">
                      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800/80 text-slate-400 mb-4 border border-slate-700/50">
                        <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z" />
                        </svg>
                      </div>
                      <h4 className="text-base font-medium text-slate-200">No projects configured yet</h4>
                      <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-slate-400">
                        Create your first project to upload source code files, scope context lines, and ask Gemini questions with strict Context Lock.
                      </p>
                      <div className="mt-6">
                        <button
                          onClick={() => {
                            setCreateError(null);
                            setShowCreateModal(true);
                          }}
                          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                          </svg>
                          Create Project
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white">Create New Project</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white"
                aria-label="Close"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Project Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. My Authentication Service"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
                  autoFocus
                />
              </div>

              {createError && (
                <div className="rounded-lg bg-rose-500/10 border border-rose-500/20 p-2.5 text-xs text-rose-300">
                  {createError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded-xl border border-slate-800 bg-slate-800/80 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreatingProject || !newProjectName.trim()}
                  className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
                >
                  {isCreatingProject ? "Creating..." : "Create Project"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Phase 9: Context Preview & Token Estimation Modal */}
      {showContextPreviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-xs">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <span>Assembled Context Preview</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    Context Lock
                  </span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Exact scope reconstructed server-side from disk before dispatching to Gemini.
                </p>
              </div>
              <button
                onClick={() => setShowContextPreviewModal(false)}
                className="text-slate-400 hover:text-white"
                aria-label="Close"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Metrics cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-center">
                <span className="text-[10px] uppercase font-mono text-slate-500">Files</span>
                <p className="text-lg font-bold text-white font-mono">{assembledContextStats.totalFiles}</p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-center">
                <span className="text-[10px] uppercase font-mono text-slate-500">Lines</span>
                <p className="text-lg font-bold text-indigo-400 font-mono">{assembledContextStats.totalLines}</p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-center">
                <span className="text-[10px] uppercase font-mono text-slate-500">Characters</span>
                <p className="text-lg font-bold text-slate-200 font-mono">~{assembledContextStats.totalChars}</p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-center">
                <span className="text-[10px] uppercase font-mono text-slate-500">Est. Tokens</span>
                <p className="text-lg font-bold text-emerald-400 font-mono">~{assembledContextStats.estimatedTokens}</p>
              </div>
            </div>

            {/* Itemized Scoped Files */}
            <div className="flex-1 overflow-y-auto space-y-2 border border-slate-800/80 rounded-xl bg-slate-950/40 p-3 my-2">
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block mb-1">
                Selected Evidence Items ({assembledContextStats.items.length}):
              </span>
              {assembledContextStats.items.map((item) => (
                <div
                  key={item.fileId}
                  className="flex items-center justify-between p-2 rounded-lg bg-slate-900 border border-slate-800/80 text-xs font-mono"
                >
                  <span className="text-white truncate max-w-xs">{item.relativePath}</span>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-indigo-500/10 text-indigo-300 px-2 py-0.5 text-[10px] border border-indigo-500/20">
                      {item.linesScoped}
                    </span>
                    <span className="text-slate-500 text-[10px]">
                      ({item.lineCount} lines)
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <span className="text-[11px] text-slate-500">
                Context Lock reconstructs lines directly from disk on request.
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowContextPreviewModal(false)}
                  className="rounded-xl border border-slate-800 bg-slate-800 px-3.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await handleSaveContext();
                    setShowContextPreviewModal(false);
                    setWorkspaceTab("chat");
                  }}
                  className="rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-sm"
                >
                  Lock Context & Open Chat &rarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
