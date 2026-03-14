"use client";

import useSWR from "swr";
import { fetchJobs } from "@/lib/api";
import type { PaginatedJobs } from "@/types";

export function useJobs(params?: {
  status?: string;
  page?: number;
  search?: string;
}) {
  const key = ["jobs", params?.status, params?.page, params?.search];

  const { data, error, isLoading, mutate } = useSWR<PaginatedJobs>(
    key,
    () => fetchJobs(params),
    { refreshInterval: 5000 }
  );

  return { data, error, isLoading, mutate };
}
