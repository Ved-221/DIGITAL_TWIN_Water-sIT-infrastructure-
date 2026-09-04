export type Currency = 'USD' | 'INR';

export const USD_TO_INR_RATE = 83.5;

/**
 * Formats a monetary amount into USD ($) or INR (₹).
 * Supports standard Indian denomination formatting (Lakhs / Crores).
 */
export function formatCurrency(amount: number, currency: Currency = 'USD', suffixMonthly: boolean = false): string {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return currency === 'USD' ? (suffixMonthly ? '$0/mo' : '$0') : (suffixMonthly ? '₹0/mo' : '₹0');
  }

  const suffix = suffixMonthly ? '/mo' : '';

  if (currency === 'INR') {
    const inrVal = amount * USD_TO_INR_RATE;
    const absVal = Math.abs(inrVal);
    const sign = inrVal < 0 ? '-' : '';

    if (absVal >= 10000000) {
      return `${sign}₹${(absVal / 10000000).toFixed(2)} Cr${suffix}`;
    }
    if (absVal >= 100000) {
      return `${sign}₹${(absVal / 100000).toFixed(2)} L${suffix}`;
    }
    return `${sign}₹${Math.round(absVal).toLocaleString('en-IN')}${suffix}`;
  }

  // USD formatting
  const absVal = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';

  if (absVal >= 1000000) {
    return `${sign}$${(absVal / 1000000).toFixed(2)}M${suffix}`;
  }
  if (absVal >= 10000) {
    return `${sign}$${(absVal / 1000).toFixed(1)}k${suffix}`;
  }
  return `${sign}$${Math.round(absVal).toLocaleString('en-US')}${suffix}`;
}
