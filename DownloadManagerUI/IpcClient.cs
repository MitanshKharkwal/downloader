using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using DownloadManagerUI.Models;
using System.Collections.ObjectModel;

namespace DownloadManagerUI;

public class IpcClient
{
    private readonly HttpClient _client = new();
    private string _port = "";
    private string _token = "";

    public IpcClient()
    {
        LoadToken();
    }

    private void LoadToken()
    {
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var tokenPath = Path.Combine(appData, ".download_manager", "ipc_token.txt");
        if (File.Exists(tokenPath))
        {
            _token = File.ReadAllText(tokenPath).Trim();
            // We assume port 47821 for now as per default
            _port = "47821";
            _client.DefaultRequestHeaders.Add("X-Auth-Token", _token);
        }
    }

    private async Task<JsonElement> SendRpc(string method, object? args = null)
    {
        if (string.IsNullOrEmpty(_token)) LoadToken();
        var url = $"http://127.0.0.1:{_port}/rpc";
        var payload = new { method, args = args ?? new { } };
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await _client.PostAsync(url, content);
        response.EnsureSuccessStatusCode();
        
        var respString = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<JsonElement>(respString);
    }

    public async Task<List<DownloadTask>> ListTasksAsync()
    {
        try
        {
            var res = await SendRpc("list_tasks");
            if (res.TryGetProperty("tasks", out var tasksElement))
            {
                return JsonSerializer.Deserialize<List<DownloadTask>>(tasksElement.GetRawText(), 
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? new List<DownloadTask>();
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"ListTasksAsync failed: {ex.Message}");
        }
        return new List<DownloadTask>();
    }

    public async Task AddTaskAsync(string url)
    {
        // Add endpoint uses legacy path for now or we can use RPC
        var apiUrl = $"http://127.0.0.1:{_port}/add";
        var payload = new { source = url };
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        await _client.PostAsync(apiUrl, content);
    }

    public async Task PauseTaskAsync(string id) => await SendRpc("pause", new { task_id = id });
    public async Task ResumeTaskAsync(string id) => await SendRpc("resume", new { task_id = id });
    public async Task CancelTaskAsync(string id) => await SendRpc("cancel", new { task_id = id });
    public async Task ClearFinishedAsync() => await SendRpc("clear_finished");
}
