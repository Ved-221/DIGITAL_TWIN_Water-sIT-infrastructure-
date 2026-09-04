/**
 * India-First Localization & Configuration Utility
 * 
 * Provides centralized Indian formatting for:
 * - Currency (INR / ₹) via Intl.NumberFormat('en-IN')
 * - Number grouping (e.g. 1,00,000)
 * - Date & Time in Asia/Kolkata (IST)
 * - Centralized AWS Region Catalog with India regions (Mumbai & Hyderabad) prominent
 * - Sourced cost labeling (Actual AWS, Converted, Configured, Simulated)
 */

export const DEFAULT_USD_TO_INR_RATE = 84.0;

export interface RegionConfig {
  id: string;
  name: string;
  country: string;
  continent: string;
  displayName: string;
  isIndia: boolean;
  group: 'India' | 'Asia Pacific' | 'US' | 'Europe' | 'Middle East' | 'Africa' | 'Canada' | 'South America';
}

export const AWS_REGIONS: RegionConfig[] = [
  // --- India (Prominently First) ---
  {
    id: 'ap-south-1',
    name: 'Mumbai',
    country: 'India',
    continent: 'Asia Pacific',
    displayName: 'Mumbai, India (ap-south-1)',
    isIndia: true,
    group: 'India'
  },
  {
    id: 'ap-south-2',
    name: 'Hyderabad',
    country: 'India',
    continent: 'Asia Pacific',
    displayName: 'Hyderabad, India (ap-south-2)',
    isIndia: true,
    group: 'India'
  },

  // --- Asia Pacific ---
  {
    id: 'ap-southeast-1',
    name: 'Singapore',
    country: 'Singapore',
    continent: 'Asia Pacific',
    displayName: 'Singapore (ap-southeast-1)',
    isIndia: false,
    group: 'Asia Pacific'
  },
  {
    id: 'ap-southeast-2',
    name: 'Sydney',
    country: 'Australia',
    continent: 'Asia Pacific',
    displayName: 'Sydney, Australia (ap-southeast-2)',
    isIndia: false,
    group: 'Asia Pacific'
  },
  {
    id: 'ap-northeast-1',
    name: 'Tokyo',
    country: 'Japan',
    continent: 'Asia Pacific',
    displayName: 'Tokyo, Japan (ap-northeast-1)',
    isIndia: false,
    group: 'Asia Pacific'
  },
  {
    id: 'ap-northeast-2',
    name: 'Seoul',
    country: 'South Korea',
    continent: 'Asia Pacific',
    displayName: 'Seoul, South Korea (ap-northeast-2)',
    isIndia: false,
    group: 'Asia Pacific'
  },
  {
    id: 'ap-east-1',
    name: 'Hong Kong',
    country: 'Hong Kong',
    continent: 'Asia Pacific',
    displayName: 'Hong Kong (ap-east-1)',
    isIndia: false,
    group: 'Asia Pacific'
  },

  // --- US ---
  {
    id: 'us-east-1',
    name: 'N. Virginia',
    country: 'United States',
    continent: 'North America',
    displayName: 'N. Virginia, US (us-east-1)',
    isIndia: false,
    group: 'US'
  },
  {
    id: 'us-east-2',
    name: 'Ohio',
    country: 'United States',
    continent: 'North America',
    displayName: 'Ohio, US (us-east-2)',
    isIndia: false,
    group: 'US'
  },
  {
    id: 'us-west-1',
    name: 'N. California',
    country: 'United States',
    continent: 'North America',
    displayName: 'N. California, US (us-west-1)',
    isIndia: false,
    group: 'US'
  },
  {
    id: 'us-west-2',
    name: 'Oregon',
    country: 'United States',
    continent: 'North America',
    displayName: 'Oregon, US (us-west-2)',
    isIndia: false,
    group: 'US'
  },

  // --- Europe ---
  {
    id: 'eu-west-1',
    name: 'Ireland',
    country: 'Ireland',
    continent: 'Europe',
    displayName: 'Ireland (eu-west-1)',
    isIndia: false,
    group: 'Europe'
  },
  {
    id: 'eu-central-1',
    name: 'Frankfurt',
    country: 'Germany',
    continent: 'Europe',
    displayName: 'Frankfurt, Germany (eu-central-1)',
    isIndia: false,
    group: 'Europe'
  },
  {
    id: 'eu-west-2',
    name: 'London',
    country: 'United Kingdom',
    continent: 'Europe',
    displayName: 'London, UK (eu-west-2)',
    isIndia: false,
    group: 'Europe'
  },
  {
    id: 'eu-north-1',
    name: 'Stockholm',
    country: 'Sweden',
    continent: 'Europe',
    displayName: 'Stockholm, Sweden (eu-north-1)',
    isIndia: false,
    group: 'Europe'
  },

  // --- Middle East ---
  {
    id: 'me-south-1',
    name: 'Bahrain',
    country: 'Bahrain',
    continent: 'Middle East',
    displayName: 'Bahrain (me-south-1)',
    isIndia: false,
    group: 'Middle East'
  },
  {
    id: 'me-central-1',
    name: 'UAE',
    country: 'UAE',
    continent: 'Middle East',
    displayName: 'UAE (me-central-1)',
    isIndia: false,
    group: 'Middle East'
  },

  // --- Africa ---
  {
    id: 'af-south-1',
    name: 'Cape Town',
    country: 'South Africa',
    continent: 'Africa',
    displayName: 'Cape Town, South Africa (af-south-1)',
    isIndia: false,
    group: 'Africa'
  },

  // --- Canada ---
  {
    id: 'ca-central-1',
    name: 'Central',
    country: 'Canada',
    continent: 'North America',
    displayName: 'Central, Canada (ca-central-1)',
    isIndia: false,
    group: 'Canada'
  },

  // --- South America ---
  {
    id: 'sa-east-1',
    name: 'São Paulo',
    country: 'Brazil',
    continent: 'South America',
    displayName: 'São Paulo, Brazil (sa-east-1)',
    isIndia: false,
    group: 'South America'
  }
];

export const REGION_MAP: Record<string, RegionConfig> = AWS_REGIONS.reduce((acc, r) => {
  acc[r.id] = r;
  return acc;
}, {} as Record<string, RegionConfig>);

/**
 * Returns a human-friendly region display name (e.g. "Mumbai, India (ap-south-1)").
 */
export function getRegionDisplayName(regionId?: string | null): string {
  if (!regionId) return 'Mumbai, India (ap-south-1)';
  const matched = REGION_MAP[regionId.toLowerCase()];
  if (matched) return matched.displayName;
  return regionId;
}

/**
 * Formats a number as Indian Currency (INR / ₹) using Intl.NumberFormat('en-IN')
 */
export function formatINR(
  amount: number | null | undefined, 
  options?: { showPaisa?: boolean; compact?: boolean }
): string {
  const value = Number(amount) || 0;
  
  if (options?.compact) {
    if (Math.abs(value) >= 1_00_00_000) {
      return `₹${(value / 1_00_00_000).toFixed(2)} Cr`;
    }
    if (Math.abs(value) >= 1_00_000) {
      return `₹${(value / 1_00_000).toFixed(2)} Lakh`;
    }
  }

  const formatter = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: options?.showPaisa ? 2 : 0,
    maximumFractionDigits: options?.showPaisa ? 2 : 0,
  });

  return formatter.format(value);
}

/**
 * Formats a number with Indian grouping commas (e.g. 1,00,000)
 */
export function formatIndianNumber(num: number | null | undefined): string {
  const value = Number(num) || 0;
  return new Intl.NumberFormat('en-IN').format(value);
}

/**
 * Formats date and time timezone-aware in Asia/Kolkata (IST)
 * Output example: "04 Sep 2026, 10:30 AM IST"
 */
export function formatISTDateTime(dateInput: string | number | Date | null | undefined): string {
  if (!dateInput) return 'Unavailable';
  const date = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
  if (isNaN(date.getTime())) return 'Invalid Date';

  const datePart = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).format(date);

  const timePart = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  }).format(date);

  return `${datePart}, ${timePart} IST`;
}

/**
 * Formats cost clearly distinguishing source:
 * - 'configured': Manual environment user-entered cost (in INR)
 * - 'actual': Real AWS billing (identified in USD or AWS reported currency, with optional converted INR)
 * - 'simulated': Deterministic simulation delta (e.g. +₹1,500/mo)
 * - 'estimated': Catalog fallback estimate
 */
export function formatCost(
  amount: number | null | undefined,
  type: 'actual' | 'estimated' | 'configured' | 'simulated',
  sourceCurrency: string = 'INR',
  options?: { showConverted?: boolean }
): string {
  const val = Number(amount) || 0;

  if (type === 'configured') {
    return `${formatINR(val)}/mo (Configured)`;
  }

  if (type === 'simulated') {
    const sign = val < 0 ? '-' : '+';
    return `${sign}${formatINR(Math.abs(val))}/mo (Simulated)`;
  }

  if (sourceCurrency.toUpperCase() === 'USD') {
    const usdStr = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    if (options?.showConverted) {
      const convertedInr = formatINR(val * DEFAULT_USD_TO_INR_RATE);
      return `${usdStr}/mo (ref. ~${convertedInr}/mo)`;
    }
    return `${usdStr}/mo (${type === 'actual' ? 'AWS Bill' : 'Catalog Est.'})`;
  }

  return `${formatINR(val)}/mo (${type === 'actual' ? 'Actual' : 'Estimated'})`;
}
