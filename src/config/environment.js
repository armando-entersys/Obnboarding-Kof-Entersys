/**
 * ========================================
 * ENTERSYS - Environment Configuration
 * ========================================
 *
 * Configuración centralizada de variables de entorno.
 * Todas las variables de entorno de Vite deben comenzar con VITE_
 *
 * Uso:
 * import { config } from '@/config/environment';
 * console.log(config.app.mode); // 'development', 'staging', 'production'
 */

// Modo de la aplicación
export const APP_MODE = import.meta.env.VITE_APP_MODE || 'development';
export const APP_ENV = import.meta.env.VITE_APP_ENV || 'development';

// Verificar si estamos en producción
export const IS_PRODUCTION = APP_ENV === 'production';
export const IS_STAGING = APP_ENV === 'staging';
export const IS_DEVELOPMENT = APP_ENV === 'development';

/**
 * Configuración general de la aplicación
 */
export const config = {
  // Información del ambiente
  app: {
    mode: APP_MODE,
    env: APP_ENV,
    isProd: IS_PRODUCTION,
    isStaging: IS_STAGING,
    isDev: IS_DEVELOPMENT,
    version: __APP_VERSION__ || '1.0.0',
    portalVersion: '1.0.02',
    buildTime: __BUILD_TIME__ || new Date().toISOString(),
  },

  // URLs
  urls: {
    app: import.meta.env.VITE_APP_URL || 'http://localhost:3000',
    api: import.meta.env.VITE_API_URL || 'http://localhost:4000/api',
    site: import.meta.env.VITE_SITE_URL || 'http://localhost:3000',
  },

  // Información de contacto
  contact: {
    whatsapp: import.meta.env.VITE_WHATSAPP_NUMBER || '5215625683662',
    email: import.meta.env.VITE_CONTACT_EMAIL || 'contacto@entersys.mx',
    phone: import.meta.env.VITE_CONTACT_PHONE || '+52 56 2568 3662',
  },

  // Analytics y tracking
  analytics: {
    enabled: import.meta.env.VITE_ENABLE_ANALYTICS === 'true',
    gtm: {
      id: import.meta.env.VITE_GTM_ID || '',
    },
    ga4: {
      measurementId: import.meta.env.VITE_GA4_MEASUREMENT_ID || '',
    },
    matomo: {
      url: import.meta.env.VITE_MATOMO_URL || '',
      siteId: import.meta.env.VITE_MATOMO_SITE_ID || '',
    },
    mautic: {
      url: import.meta.env.VITE_MAUTIC_URL || '',
    },
  },

  // Social Media
  social: {
    facebook: import.meta.env.VITE_FACEBOOK_URL || 'https://www.facebook.com/entersysmx',
    instagram: import.meta.env.VITE_INSTAGRAM_URL || 'https://www.instagram.com/entersysmx',
    linkedin: import.meta.env.VITE_LINKEDIN_URL || 'https://www.linkedin.com/company/entersysmx',
    youtube: import.meta.env.VITE_YOUTUBE_URL || 'https://www.youtube.com/@EntersysMX',
  },

  // Feature flags
  features: {
    debug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
    consoleLogs: import.meta.env.VITE_ENABLE_CONSOLE_LOGS === 'true',
    versionInfo: import.meta.env.VITE_SHOW_VERSION_INFO === 'true',
    errorReporting: import.meta.env.VITE_ENABLE_ERROR_REPORTING === 'true',
    webVitals: import.meta.env.VITE_ENABLE_WEB_VITALS === 'true',
    performanceMonitoring: import.meta.env.VITE_ENABLE_PERFORMANCE_MONITORING === 'true',
  },

  // SEO & Meta
  seo: {
    siteName: import.meta.env.VITE_SITE_NAME || 'Entersys',
    siteDescription: import.meta.env.VITE_SITE_DESCRIPTION || 'Transformamos operaciones empresariales',
    siteUrl: import.meta.env.VITE_SITE_URL || 'http://localhost:3000',
  },
};

/**
 * Helper para logging condicional basado en el ambiente
 */
export const logger = {
  log: (...args) => {
    if (config.features.consoleLogs) {
      console.log('[Entersys]', ...args);
    }
  },
  error: (...args) => {
    if (config.features.debug || config.app.isProd) {
      console.error('[Entersys Error]', ...args);
    }
  },
  warn: (...args) => {
    if (config.features.debug) {
      console.warn('[Entersys Warning]', ...args);
    }
  },
  debug: (...args) => {
    if (config.features.debug) {
      console.debug('[Entersys Debug]', ...args);
    }
  },
};

/**
 * Validación de configuración
 * Se ejecuta solo una vez al importar el módulo
 */
if (config.features.debug) {
  logger.log('Environment Configuration Loaded:', {
    mode: config.app.mode,
    env: config.app.env,
    version: config.app.version,
    analyticsEnabled: config.analytics.enabled,
  });

  // Advertencias si falta configuración crítica
  if (!config.urls.api) {
    logger.warn('API URL not configured');
  }

  if (config.analytics.enabled && !config.analytics.matomo.siteId) {
    logger.warn('Analytics enabled but Matomo Site ID not configured');
  }
}

// Export por defecto
export default config;
