/** 书源列表状态管理。 */

import { create } from "zustand"
import type { BookSource } from "@/types/source"

interface SourceStore {
  sources: BookSource[]
  totalCount: number
  isLoading: boolean
  filters: {
    search: string
    status: string
    page: number
    pageSize: number
  }
  setSources: (sources: BookSource[], total: number) => void
  setLoading: (loading: boolean) => void
  setFilters: (filters: Partial<SourceStore["filters"]>) => void
  resetFilters: () => void
}

const defaultFilters = {
  search: "",
  status: "",
  page: 1,
  pageSize: 20,
}

export const useSourceStore = create<SourceStore>()((set) => ({
  sources: [],
  totalCount: 0,
  isLoading: false,
  filters: { ...defaultFilters },

  setSources: (sources, total) =>
    set({ sources, totalCount: total, isLoading: false }),

  setLoading: (isLoading) => set({ isLoading }),

  setFilters: (filters) =>
    set((state) => ({
      filters: { ...state.filters, ...filters },
    })),

  resetFilters: () =>
    set({ filters: { ...defaultFilters } }),
}))
