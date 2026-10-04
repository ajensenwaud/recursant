#include "recursant/catalog.h"
#include <string.h>

/* Public gateways with an OpenAI-compatible chat-completions endpoint (base
 * URLs as published by each provider; cross-checked against Hermes' provider
 * plugins, 2026-10). Excluded on purpose: providers that need OAuth or a
 * cloud SDK (Bedrock, Vertex, Copilot, Codex, Nous Portal, Qwen OAuth), a
 * per-deployment URL (Azure AI Foundry: add it as a custom provider) or a
 * non-chat-completions API (Responses-only gateways). Only OpenRouter has a
 * dedicated adapter; every other entry uses the strict OpenAI shape. */
static const rc_catalog_entry entries[] = {
    { "openrouter",   "OpenRouter",                       "https://openrouter.ai/api/v1",                              "OPENROUTER_API_KEY",   "openrouter" },
    { "openai",       "OpenAI",                           "https://api.openai.com/v1",                                 "OPENAI_API_KEY",       "openai-compatible" },
    { "anthropic",    "Anthropic (OpenAI-compatible API)", "https://api.anthropic.com/v1",                             "ANTHROPIC_API_KEY",    "openai-compatible" },
    { "gemini",       "Google Gemini (OpenAI-compatible)", "https://generativelanguage.googleapis.com/v1beta/openai",  "GEMINI_API_KEY",       "openai-compatible" },
    { "xai",          "xAI",                              "https://api.x.ai/v1",                                       "XAI_API_KEY",          "openai-compatible" },
    { "deepseek",     "DeepSeek",                         "https://api.deepseek.com/v1",                               "DEEPSEEK_API_KEY",     "openai-compatible" },
    { "mistral",      "Mistral",                          "https://api.mistral.ai/v1",                                 "MISTRAL_API_KEY",      "openai-compatible" },
    { "groq",         "Groq",                             "https://api.groq.com/openai/v1",                            "GROQ_API_KEY",         "openai-compatible" },
    { "together",     "Together AI",                      "https://api.together.xyz/v1",                               "TOGETHER_API_KEY",     "openai-compatible" },
    { "fireworks",    "Fireworks",                        "https://api.fireworks.ai/inference/v1",                     "FIREWORKS_API_KEY",    "openai-compatible" },
    { "deepinfra",    "DeepInfra",                        "https://api.deepinfra.com/v1/openai",                       "DEEPINFRA_API_KEY",    "openai-compatible" },
    { "cerebras",     "Cerebras",                         "https://api.cerebras.ai/v1",                                "CEREBRAS_API_KEY",     "openai-compatible" },
    { "nvidia",       "NVIDIA NIM",                       "https://integrate.api.nvidia.com/v1",                       "NVIDIA_API_KEY",       "openai-compatible" },
    { "huggingface",  "Hugging Face Inference Providers", "https://router.huggingface.co/v1",                          "HF_TOKEN",             "openai-compatible" },
    { "novita",       "Novita AI",                        "https://api.novita.ai/openai/v1",                           "NOVITA_API_KEY",       "openai-compatible" },
    { "nebius",       "Nebius Token Factory",             "https://api.tokenfactory.nebius.com/v1",                    "NEBIUS_API_KEY",       "openai-compatible" },
    { "ai-gateway",   "Vercel AI Gateway",                "https://ai-gateway.vercel.sh/v1",                           "AI_GATEWAY_API_KEY",   "openai-compatible" },
    { "zai",          "Z.ai (GLM)",                       "https://api.z.ai/api/paas/v4",                              "ZAI_API_KEY",          "openai-compatible" },
    { "moonshot",     "Moonshot AI (Kimi)",               "https://api.moonshot.ai/v1",                                "MOONSHOT_API_KEY",     "openai-compatible" },
    { "minimax",      "MiniMax",                          "https://api.minimax.io/v1",                                 "MINIMAX_API_KEY",      "openai-compatible" },
    { "alibaba",      "Alibaba Cloud Model Studio",       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",    "DASHSCOPE_API_KEY",    "openai-compatible" },
    { "ollama-cloud", "Ollama Cloud",                     "https://ollama.com/v1",                                     "OLLAMA_API_KEY",       "openai-compatible" },
    { "arcee",        "Arcee AI",                         "https://api.arcee.ai/api/v1",                               "ARCEEAI_API_KEY",      "openai-compatible" },
    { "kilocode",     "Kilo Gateway",                     "https://api.kilo.ai/api/gateway",                           "KILOCODE_API_KEY",     "openai-compatible" },
    { "opencode-zen", "OpenCode Zen",                     "https://opencode.ai/zen/v1",                                "OPENCODE_ZEN_API_KEY", "openai-compatible" },
    { "upstage",      "Upstage",                          "https://api.upstage.ai/v1",                                 "UPSTAGE_API_KEY",      "openai-compatible" },
    { "gmi",          "GMI Cloud",                        "https://api.gmi-serving.com/v1",                            "GMI_API_KEY",          "openai-compatible" },
    { "xiaomi",       "Xiaomi MiMo",                      "https://api.xiaomimimo.com/v1",                             "XIAOMI_API_KEY",       "openai-compatible" },
};

const rc_catalog_entry *rc_catalog(size_t *count) {
    *count = sizeof entries / sizeof *entries;
    return entries;
}

const rc_catalog_entry *rc_catalog_find(const char *name) {
    for (size_t i = 0; name && i < sizeof entries / sizeof *entries; i++)
        if (!strcmp(entries[i].name, name)) return &entries[i];
    return NULL;
}
