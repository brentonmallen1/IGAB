import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { TagColorSlot } from '../components/common/TagChip';

export interface Tag {
  id: string;
  name: string;
  system_key: string | null;
  color_slot: TagColorSlot | null;
  category_count: number;
  payee_count: number;
}

export interface TagSimple {
  id: string;
  name: string;
  color_slot: TagColorSlot | null;
}

export function useTags(budgetId: string | null) {
  return useQuery({
    queryKey: ['tags', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<Tag[]>(`/${budgetId}/tags`);
      return data;
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  });
}

export function useCreateTag(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; color_slot?: TagColorSlot | null }) =>
      apiClient.post<Tag>(`/${budgetId}/tags`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags', budgetId] }),
  });
}

export function useUpdateTag(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; color_slot?: TagColorSlot | null }) =>
      apiClient.patch<Tag>(`/${budgetId}/tags/${id}`, body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags', budgetId] });
      qc.invalidateQueries({ queryKey: ['categories', budgetId] });
      // Tags are a classification override, so the "Counts as" badge
      // changes with them. Its key is not under ['categories'].
      qc.invalidateQueries({ queryKey: ['categoryClassification'] });
      qc.invalidateQueries({ queryKey: ['payees', budgetId] });
    },
  });
}

export function useDeleteTag(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/${budgetId}/tags/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags', budgetId] });
      qc.invalidateQueries({ queryKey: ['categories', budgetId] });
      // Tags are a classification override, so the "Counts as" badge
      // changes with them. Its key is not under ['categories'].
      qc.invalidateQueries({ queryKey: ['categoryClassification'] });
      qc.invalidateQueries({ queryKey: ['payees', budgetId] });
    },
  });
}

export function useSetCategoryTags(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ categoryId, tagIds }: { categoryId: string; tagIds: string[] }) =>
      apiClient.put<TagSimple[]>(`/${budgetId}/categories/${categoryId}/tags`, { tag_ids: tagIds }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', budgetId] });
      // Tags are a classification override, so the "Counts as" badge
      // changes with them. Its key is not under ['categories'].
      qc.invalidateQueries({ queryKey: ['categoryClassification'] });
      qc.invalidateQueries({ queryKey: ['tags', budgetId] });
    },
  });
}

export function useSetPayeeTags(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ payeeId, tagIds }: { payeeId: string; tagIds: string[] }) =>
      apiClient.put<TagSimple[]>(`/${budgetId}/payees/${payeeId}/tags`, { tag_ids: tagIds }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] });
      qc.invalidateQueries({ queryKey: ['tags', budgetId] });
    },
  });
}

export function useBulkAddPayeeTags(budgetId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ payeeIds, tagIds }: { payeeIds: string[]; tagIds: string[] }) => {
      await Promise.all(
        payeeIds.map((payeeId) =>
          apiClient.post(`/${budgetId}/payees/${payeeId}/tags/add`, { tag_ids: tagIds })
        )
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] });
      qc.invalidateQueries({ queryKey: ['tags', budgetId] });
    },
  });
}
