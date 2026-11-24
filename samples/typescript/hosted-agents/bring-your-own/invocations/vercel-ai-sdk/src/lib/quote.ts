const monthlyPrices = {
  standard: 10,
  premium: 25,
} as const;

export function calculateQuote(standardSeats: number, premiumSeats: number) {
  const standardSubtotal = standardSeats * monthlyPrices.standard;
  const premiumSubtotal = premiumSeats * monthlyPrices.premium;

  return {
    currency: "USD",
    billingPeriod: "monthly",
    standard: {
      seats: standardSeats,
      pricePerSeat: monthlyPrices.standard,
      subtotal: standardSubtotal,
    },
    premium: {
      seats: premiumSeats,
      pricePerSeat: monthlyPrices.premium,
      subtotal: premiumSubtotal,
    },
    total: standardSubtotal + premiumSubtotal,
    note: "Illustrative sample prices; replace them with your own catalog.",
  };
}
