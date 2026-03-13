export const STORAGE_KEY = "mind.frontend.apiKey";
export const INGEST_HISTORY_KEY = "mind.frontend.ingestHistory.v1";
export const UI_CONTEXT_KEY = "mind.frontend.workbenchContext.v1";
export const INGEST_PAGE_SIZE = 10;
export const LLM_ICON_MAX_DIMENSION = 192;
export const LLM_ICON_TARGET_BYTES = 96 * 1024;

export const MIN_BUSY_MS = {
  submit: 1000,
  mutate: 1000,
  refresh: 700,
  reset: 450,
  auth: 650,
};

export const DEFAULTS = {
  ingestTimestampOrder: "1",
  retrieveMaxCandidates: "10",
  offlinePriority: "0.5",
  debugLimit: "80",
  workspace: "workspace-overview",
  operation: "module-ingest",
  settingsSection: "settings-panel-general",
};

export const ENTRYPOINT_LABELS = {
  ingest: { title: "写入记忆", mode: "保存", summary: "把重要内容保存下来，便于后续继续使用。" },
  retrieve: { title: "召回检索", mode: "查找", summary: "快速找回可能相关的已保存内容。" },
  access: { title: "访问问答", mode: "整理", summary: "整合已有内容，生成更完整的回答。" },
  offline: { title: "后台任务", mode: "整理", summary: "把整理任务交给系统在后台慢慢完成。" },
  gate_demo: { title: "示例摘要", mode: "查看", summary: "集中查看常用示例、检查结果和说明内容。" },
};

export const GATE_ENTRY_LABELS = {
  demo_memory_flow: "记忆流演示",
  demo_access_flow: "访问流演示",
  demo_offline_flow: "离线流演示",
  gate_capability_readiness: "可用性检查",
  gate_telemetry_readiness: "记录完整性检查",
  report_provider_compatibility: "兼容性说明",
  report_telemetry_audit: "记录说明",
};

export const GATE_KIND_LABELS = {
  demo: "演示",
  gate: "检查",
  report: "说明",
};

export const VIEWPORT_LABELS = {
  desktop: "桌面端",
  mobile: "移动端",
};

export const SETTING_LABELS = {
  backend: "存储方式",
  profile: "运行环境",
  provider: "回答方式",
  model: "模型名称",
  endpoint: "服务地址",
  dev_mode: "高级排查",
};

export const ACCESS_DEPTH_LABELS = {
  auto: "自动选择",
  flash: "快速回答",
  focus: "聚焦回答",
  reconstruct: "完整整理",
  reflective_access: "深度整理",
};

export const OFFLINE_JOB_KIND_LABELS = {
  reflect_episode: "整理当前分组",
  promote_schema: "提炼长期规则",
};

export const PROVIDER_FAMILY_LABELS = {
  deterministic: "确定性回退",
  openai: "OpenAI",
  claude: "Claude",
  gemini: "Gemini",
};

export const ANSWER_MODE_LABELS = {
  builtin: "内建模式",
  llm: "LLM",
};

export const OPERATION_CHAIN_STATUS_LABELS = {
  idle: "待执行",
  running: "进行中",
  success: "已完成",
  fallback: "已回退",
  error: "请求失败",
};

export const OPERATION_CHAIN_STEP_STATUS_LABELS = {
  upcoming: "待执行",
  active: "进行中",
  done: "已完成",
  fallback: "已回退",
  skipped: "未触发",
  error: "出错",
};

export const OPERATION_CHAIN_CONFIG = {
  "module-ingest": {
    title: "写入记忆",
    apiPath: "/v1/frontend/ingest",
    idleSummary: "系统会接收内容、写入记忆、归入分组，并返回记录编号。",
    steps: [
      { id: "receive", label: "接收内容", summary: "系统接收你要保存的内容和分组信息。" },
      { id: "write", label: "写入对象", summary: "系统把内容写成一条可继续引用的记录。" },
      { id: "episode", label: "归入分组", summary: "系统将记录放入对应分组，并确认时间顺序。" },
      { id: "result", label: "返回记录编号", summary: "系统返回本次保存后的记录编号和版本。" },
    ],
  },
  "module-retrieve": {
    title: "召回检索",
    apiPath: "/v1/frontend/retrieve",
    idleSummary: "系统会接收问题、执行检索，并返回可能相关的候选内容。",
    steps: [
      { id: "receive", label: "接收问题", summary: "系统接收你的问题和查找范围。" },
      { id: "retrieve", label: "执行检索", summary: "系统在已保存内容中查找可能相关的记录。" },
      { id: "result", label: "返回候选内容", summary: "系统返回候选列表和查找结果。" },
    ],
  },
  "module-access": {
    title: "访问问答",
    apiPath: "/v1/frontend/access",
    idleSummary: "系统会先找内容，再选依据，最后通过内建路径或 LLM 生成回答。",
    steps: [
      { id: "receive", label: "接收问题", summary: "系统接收你的问题、回答方式和范围限制。" },
      { id: "retrieve", label: "查找候选", summary: "系统先找出与问题相关的候选内容。" },
      { id: "evidence", label: "选出依据", summary: "系统从候选中选出本次真正采用的依据。" },
      { id: "llm", label: "LLM 调用", summary: "如果当前启用了 LLM，系统会调用当前服务生成回答。", highlighted: true },
      { id: "result", label: "返回答案", summary: "系统返回最终答案，并展示本次采用了哪些内容。" },
    ],
  },
  "module-offline": {
    title: "后台任务",
    apiPath: "/v1/frontend/offline",
    idleSummary: "系统会接收整理请求、创建后台任务，并返回任务编号。",
    steps: [
      { id: "receive", label: "接收整理请求", summary: "系统接收任务类型、分组或目标内容以及优先级。" },
      { id: "create", label: "创建后台任务", summary: "系统为这次整理请求创建一个后台任务。" },
      { id: "result", label: "返回任务编号", summary: "系统返回任务编号和当前状态，后续会在后台继续处理。" },
    ],
  },
};

export const AUTH_MODE_LABELS = {
  none: "无需鉴权",
  bearer_token: "Bearer Token",
  api_key: "API Key",
};

export const PROVIDER_STATUS_LABELS = {
  available: "已就绪",
  missing_auth: "缺少密钥",
};

export const PROVIDER_EXECUTION_LABELS = {
  deterministic_adapter_ready: "内建回退已就绪",
  adapter_unavailable_missing_auth: "尚未具备调用条件",
  openai_responses_adapter_ready: "OpenAI 调用链已就绪",
  claude_messages_adapter_ready: "Claude 调用链已就绪",
  gemini_generate_content_adapter_ready: "Gemini 调用链已就绪",
  adapter_unknown: "调用状态未注明",
};

export const RETRY_POLICY_LABELS = {
  default: "标准重试",
  none: "不重试",
  aggressive: "积极重试",
};

export const LLM_PROTOCOL_LIBRARY = {
  openai: {
    name: "OpenAI",
    mark: "OA",
    accent: "openai",
    summary: "兼容 OpenAI 风格接口。",
    defaultName: "OpenAI 官方",
    defaultEndpoint: "https://api.openai.com/v1",
  },
  claude: {
    name: "Claude",
    mark: "CL",
    accent: "claude",
    summary: "兼容 Claude Messages 接口。",
    defaultName: "Claude 官方",
    defaultEndpoint: "https://api.anthropic.com/v1",
  },
  gemini: {
    name: "Gemini",
    mark: "GM",
    accent: "gemini",
    summary: "兼容 Gemini Generate Content 接口。",
    defaultName: "Gemini 官方",
    defaultEndpoint: "https://generativelanguage.googleapis.com/v1beta",
  },
};
