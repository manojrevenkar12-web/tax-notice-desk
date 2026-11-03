import { date, daysUntil, money, signed } from "./format";

test("cents are shown as euros the German way", () => {
  expect(money(123456).replace(/\s/g, " ")).toBe("1.234,56 €");
  expect(signed(-93300).replace(/\s/g, " ")).toBe("-933,00 €");
  expect(money(null)).toBe("–");
});

test("dates and days left", () => {
  expect(date("2027-01-04")).toBe("04.01.2027");
  expect(daysUntil("2027-01-04", "2026-12-28")).toBe(7);
  expect(daysUntil("2026-03-30", "2026-03-28")).toBe(2); // across the clock change
});
