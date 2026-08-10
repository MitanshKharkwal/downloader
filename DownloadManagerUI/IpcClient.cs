using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
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
        var options = new JsonSerializerOptions { TypeInfoResolver = new DefaultJsonTypeInfoResolver() };
        var json = JsonSerializer.Serialize(payload, options);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await _client.PostAsync(url, content);
        response.EnsureSuccessStatusCode();

        var respString = await response.Content.ReadAsStringAsync();
        try
        {
            var options2 = new JsonSerializerOptions { TypeInfoResolver = new DefaultJsonTypeInfoResolver() };
            return JsonSerializer.Deserialize<JsonElement>(respString, options2);
        }
        catch (Exception ex)
        {
            var logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".download_manager", "ui_errors.log");
            System.IO.File.AppendAllText(logPath, $"SendRpc parse failed for {method}. Resp: {respString}. Ex: {ex}\n");
            throw;
        }
    }

    public async Task<List<DownloadTask>> ListTasksAsync()
    {
        try
        {
            var res = await SendRpc("list_tasks");
            if (res.TryGetProperty("tasks", out var tasksElement))
            {
                var options = new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    TypeInfoResolver = new DefaultJsonTypeInfoResolver()
                };
                return JsonSerializer.Deserialize<List<DownloadTask>>(tasksElement.GetRawText(), options) ?? new List<DownloadTask>();
            }
        }
        catch (Exception ex)
        {
            var logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".download_manager", "ui_errors.log");
            System.IO.File.AppendAllText(logPath, $"ListTasksAsync failed: {ex}\n");
            System.Diagnostics.Debug.WriteLine($"ListTasksAsync failed: {ex.Message}");
        }
        return new List<DownloadTask>();
    }

    public async Task AddTaskAsync(string url)
    {
        if (string.IsNullOrEmpty(_token)) LoadToken();
        var apiUrl = $"http://127.0.0.1:{_port}/add";
        var payload = new { source = url };
        var options = new JsonSerializerOptions { TypeInfoResolver = new DefaultJsonTypeInfoResolver() };
        var json = JsonSerializer.Serialize(payload, options);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        await _client.PostAsync(apiUrl, content);
    }

    public async Task<JsonElement> FetchVideoInfoAsync(string url) => await SendRpc("fetch_video_info", new { url });
    public async Task AddVideoTaskAsync(string url, string formatId, string filename) => await SendRpc("add_video_task", new { url, format_id = formatId, filename });

    public async Task PauseTaskAsync(string id) => await SendRpc("pause", new { task_id = id });
    public async Task ResumeTaskAsync(string id) => await SendRpc("resume", new { task_id = id });
    public async Task RetryTaskAsync(string id) => await SendRpc("retry", new { task_id = id });
    public async Task CancelTaskAsync(string id) => await SendRpc("cancel", new { task_id = id });
    public async Task ClearFinishedAsync() => await SendRpc("clear_finished");

    public async Task PauseAllAsync() => await SendRpc("pause_all");
    public async Task ResumeAllAsync() => await SendRpc("resume_all");

    public async Task<AppConfig> GetConfigAsync()
    {
        var res = await SendRpc("get_config");
        if (res.TryGetProperty("config", out var configElement))
        {
            var options = new JsonSerializerOptions { TypeInfoResolver = new DefaultJsonTypeInfoResolver() };
            return JsonSerializer.Deserialize<AppConfig>(configElement.GetRawText(), options) ?? new AppConfig();
        }
        return new AppConfig();
    }

    public async Task SetConfigAsync(AppConfig config) => await SendRpc("set_config", new { config });

    public async Task ShutdownAsync() => await SendRpc("shutdown");
}
