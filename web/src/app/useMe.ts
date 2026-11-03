import { useQuery } from "@tanstack/react-query";
import { api } from "../shared/api/client";
import type { Me } from "../shared/api/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: 60_000 });
}

export function todayOf(me: Me | undefined): string {
  return me?.today ?? new Date().toISOString().slice(0, 10);
}
