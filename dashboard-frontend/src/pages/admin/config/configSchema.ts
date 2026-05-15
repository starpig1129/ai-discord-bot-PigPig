export type FieldType = 'text' | 'number' | 'boolean' | 'select' | 'array' | 'textarea';

const BANNED_PATH_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

function assertSafePathKey(key: string): void {
  if (BANNED_PATH_KEYS.has(key)) {
    throw new Error(`Unsafe path segment: "${key}"`);
  }
}

export interface ConfigFieldDef {
  /** Dot-notation path into the config object, e.g. "dashboard.port" */
  path: string;
  /** i18n translation key for the label shown in the form */
  labelKey: string;
  type: FieldType;
  /** Only for 'select' fields — list of valid option strings */
  options?: string[];
  /** Only for 'number' fields */
  min?: number;
  max?: number;
  /** Shows value but disables editing */
  readOnly?: boolean;
  /** i18n key for the section header this field belongs to */
  section: string;
}

export type AllConfigSchemas = Record<string, ConfigFieldDef[]>;

export const CONFIG_SCHEMAS: AllConfigSchemas = {
  base: [
    {
      path: 'version',
      labelKey: 'config.fields.version',
      type: 'text',
      readOnly: true,
      section: 'config.sections.bot',
    },
    {
      path: 'prefix',
      labelKey: 'config.fields.prefix',
      type: 'text',
      section: 'config.sections.bot',
    },
    {
      path: 'dashboard.enabled',
      labelKey: 'config.fields.dashboard_enabled',
      type: 'boolean',
      section: 'config.sections.dashboard',
    },
    {
      path: 'dashboard.port',
      labelKey: 'config.fields.dashboard_port',
      type: 'number',
      min: 1,
      max: 65535,
      section: 'config.sections.dashboard',
    },
    {
      path: 'dashboard.cors_origins',
      labelKey: 'config.fields.dashboard_cors_origins',
      type: 'array',
      section: 'config.sections.dashboard',
    },
    {
      path: 'logging.console.level',
      labelKey: 'config.fields.logging_level',
      type: 'select',
      options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      section: 'config.sections.logging',
    },
    {
      path: 'logging.rotation.retention_days',
      labelKey: 'config.fields.logging_retention',
      type: 'number',
      min: 1,
      max: 3650,
      section: 'config.sections.logging',
    },
  ],

  llm: [
    {
      path: 'llm_call_timeout',
      labelKey: 'config.fields.llm_timeout',
      type: 'number',
      min: 10,
      max: 600,
      section: 'config.sections.llm_simple',
    },
    {
      path: 'google_search_agent',
      labelKey: 'config.fields.google_search_agent',
      type: 'text',
      section: 'config.sections.llm_simple',
    },
    {
      path: 'model_priorities',
      labelKey: 'config.fields.model_priorities',
      type: 'textarea',
      section: 'config.sections.model_priorities',
    },
  ],

  memory: [
    {
      path: 'enabled',
      labelKey: 'config.fields.memory_enabled',
      type: 'boolean',
      section: 'config.sections.memory_basic',
    },
    {
      path: 'procedural_cache_ttl',
      labelKey: 'config.fields.cache_ttl',
      type: 'number',
      min: 0,
      section: 'config.sections.memory_basic',
    },
    {
      path: 'vector_store_type',
      labelKey: 'config.fields.vector_store_type',
      type: 'select',
      options: ['qdrant', 'in_memory'],
      section: 'config.sections.vector_store',
    },
    {
      path: 'qdrant_url',
      labelKey: 'config.fields.qdrant_url',
      type: 'text',
      section: 'config.sections.vector_store',
    },
    {
      path: 'qdrant_collection_name',
      labelKey: 'config.fields.qdrant_collection',
      type: 'text',
      section: 'config.sections.vector_store',
    },
    {
      path: 'embedding_provider',
      labelKey: 'config.fields.embedding_provider',
      type: 'select',
      options: ['google', 'openai', 'ollama', 'huggingface'],
      section: 'config.sections.embedding',
    },
    {
      path: 'embedding_model_name',
      labelKey: 'config.fields.embedding_model',
      type: 'text',
      section: 'config.sections.embedding',
    },
    {
      path: 'embedding_dim',
      labelKey: 'config.fields.embedding_dim',
      type: 'number',
      min: 1,
      section: 'config.sections.embedding',
    },
    {
      path: 'ollama_url',
      labelKey: 'config.fields.ollama_url',
      type: 'text',
      section: 'config.sections.embedding',
    },
    {
      path: 'vector_search_k',
      labelKey: 'config.fields.vector_search_k',
      type: 'number',
      min: 1,
      max: 50,
      section: 'config.sections.processing',
    },
    {
      path: 'keyword_search_k',
      labelKey: 'config.fields.keyword_search_k',
      type: 'number',
      min: 1,
      max: 50,
      section: 'config.sections.processing',
    },
    {
      path: 'message_threshold',
      labelKey: 'config.fields.msg_threshold',
      type: 'number',
      min: 1,
      section: 'config.sections.processing',
    },
    {
      path: 'time_threshold',
      labelKey: 'config.fields.time_threshold',
      type: 'number',
      min: 60,
      section: 'config.sections.processing',
    },
    {
      path: 'processing_concurrency',
      labelKey: 'config.fields.processing_concurrency',
      type: 'number',
      min: 1,
      max: 10,
      section: 'config.sections.processing',
    },
    {
      path: 'processing_delay',
      labelKey: 'config.fields.processing_delay',
      type: 'number',
      min: 0,
      section: 'config.sections.processing',
    },
  ],

  music: [
    {
      path: 'music_temp_base',
      labelKey: 'config.fields.music_temp_base',
      type: 'text',
      section: 'config.sections.music_general',
    },
    {
      path: 'youtube_cookies_path',
      labelKey: 'config.fields.cookies_path',
      type: 'text',
      section: 'config.sections.music_general',
    },
    {
      path: 'ffmpeg.location',
      labelKey: 'config.fields.ffmpeg_location',
      type: 'text',
      section: 'config.sections.ffmpeg',
    },
    {
      path: 'ffmpeg.audio_quality',
      labelKey: 'config.fields.audio_quality',
      type: 'select',
      options: ['128', '192', '256', '320'],
      section: 'config.sections.ffmpeg',
    },
    {
      path: 'ffmpeg.audio_codec',
      labelKey: 'config.fields.audio_codec',
      type: 'select',
      options: ['mp3', 'aac', 'ogg'],
      section: 'config.sections.ffmpeg',
    },
  ],
};

/**
 * Read a value from a nested object using dot-notation path.
 * e.g. getNestedValue({a: {b: 1}}, "a.b") === 1
 */
export function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  if (!path) throw new Error('path must be a non-empty string');
  return path.split('.').reduce(
    (acc: unknown, key: string) => {
      assertSafePathKey(key);
      return acc !== null && acc !== undefined && typeof acc === 'object'
        ? (acc as Record<string, unknown>)[key]
        : undefined;
    },
    obj,
  );
}

/**
 * Return a deep clone of `obj` with the value at dot-notation `path` set to `value`.
 * Creates intermediate objects if they don't exist.
 */
export function setNestedValue(
  obj: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  if (!path) throw new Error('path must be a non-empty string');
  const result = JSON.parse(JSON.stringify(obj)) as Record<string, unknown>;
  const keys = path.split('.');
  let cur: Record<string, unknown> = result;
  for (let i = 0; i < keys.length - 1; i++) {
    assertSafePathKey(keys[i]);
    if (typeof cur[keys[i]] !== 'object' || cur[keys[i]] === null) {
      cur[keys[i]] = {};
    }
    cur = cur[keys[i]] as Record<string, unknown>;
  }
  assertSafePathKey(keys[keys.length - 1]);
  cur[keys[keys.length - 1]] = value;
  return result;
}
