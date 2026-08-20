import { format } from "date-fns";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/;

export function parseFormDate(value: string): Date | undefined {
  const match = ISO_DATE.exec(value.trim());
  if (!match) {
    return undefined;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hours = match[4] ? Number(match[4]) : 0;
  const minutes = match[5] ? Number(match[5]) : 0;
  const date = new Date(year, month - 1, day, hours, minutes);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

export function toFormDate(date: Date, includeTime = false): string {
  const day = format(date, "yyyy-MM-dd");
  if (!includeTime) {
    return day;
  }
  return `${day}T${format(date, "HH:mm")}`;
}

export function formatFormDate(value: string, includeTime = false): string {
  const date = parseFormDate(value);
  if (!date) {
    return "";
  }
  return includeTime ? format(date, "PPP p") : format(date, "PPP");
}
