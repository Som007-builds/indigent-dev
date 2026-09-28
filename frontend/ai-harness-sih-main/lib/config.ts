import appConfig from "@/config/app-config.json"

export type AppConfig = typeof appConfig

export const config: AppConfig = appConfig

export const {
  project,
  branding,
  navigation,
  sovereignty: sovereigntyConfig,
  approvalGate: approvalGateConfig,
  contextTabs: contextTabsConfig,
  documents: documentsConfig,
  knowledge: knowledgeConfig,
  models: modelsConfig,
  audit: auditConfig,
  pid: pidConfig,
  workbench: workbenchConfig,
} = appConfig

export default config
