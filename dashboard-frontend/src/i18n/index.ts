/**
 * i18next configuration for the PigPig Dashboard.
 * Supports Traditional Chinese (zh-TW) and English (en).
 * Language preference is persisted to localStorage via LanguageDetector.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zhTW from './locales/zh-TW.json';
import en from './locales/en.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-TW': { translation: zhTW },
      en: { translation: en },
    },
    // Fallback order: zh-TW first (bot's primary audience)
    fallbackLng: 'zh-TW',
    supportedLngs: ['zh-TW', 'en'],
    // Map generic 'zh' to 'zh-TW'
    load: 'currentOnly',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'pigpig_dashboard_lang',
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

export default i18n;

/** Available language options for the language switcher. */
export const LANGUAGES = [
  { code: 'zh-TW', label: '繁體中文', flag: '🇹🇼' },
  { code: 'en',    label: 'English',  flag: '🇺🇸' },
] as const;
