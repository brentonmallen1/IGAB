import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import type { User } from '../types'
import { ROOT } from './queryKeys'

export interface LoginCredentials {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
}

export async function login(creds: LoginCredentials): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/login', creds)
  return data
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me')
  return data
}

export function useCurrentUser() {
  return useQuery({
    queryKey: [ROOT.currentUser],
    queryFn: fetchCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

export function useLogin() {
  return useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
    },
  })
}

export function useLogout() {
  return () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
  }
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiClient.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}
