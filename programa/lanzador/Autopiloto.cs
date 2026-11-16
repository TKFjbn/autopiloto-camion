// Lanzador de Autopiloto (3.4.0). Hace lo mismo que Autopiloto.bat: busca Python y abre programa\arranque.py
// sin ventana negra. Se compila en el PC del usuario con "Crear Autopiloto.exe.bat" (compilador de C# de Windows).
// No toca el juego ni su carpeta.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Lanzador
{
    static string Buscar(string nombre)
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string d in path.Split(';'))
        {
            try
            {
                string c = Path.Combine(d.Trim().Trim('"'), nombre);
                if (d.Trim().Length > 0 && File.Exists(c)) return c;
            }
            catch (Exception) { }
        }
        string win = Environment.GetEnvironmentVariable("WINDIR") ?? "C:\\Windows";
        string enWin = Path.Combine(win, nombre);          // el lanzador "py"/"pyw" se instala en C:\Windows
        return File.Exists(enWin) ? enWin : null;
    }

    [STAThread]
    static int Main()
    {
        string raiz = AppDomain.CurrentDomain.BaseDirectory;
        string programa = Path.Combine(raiz, "programa");
        string arranque = Path.Combine(programa, "arranque.py");
        if (!File.Exists(arranque))
        {
            MessageBox.Show("No encuentro programa\\arranque.py.\n\nAutopiloto.exe tiene que estar en la carpeta " +
                            "del autopiloto (junto a Autopiloto.bat).", "Autopiloto",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string py = null;
        foreach (string n in new string[] { "pythonw.exe", "pyw.exe", "python.exe", "py.exe" })
        {
            py = Buscar(n);
            if (py != null) break;
        }
        if (py == null)
        {
            MessageBox.Show("No se encontró Python en este PC.\n\nInstala Python 3.12 desde python.org y en el " +
                            "instalador marca \"Add python.exe to PATH\".", "Autopiloto",
                            MessageBoxButtons.OK, MessageBoxIcon.Warning);
            try { Process.Start("https://www.python.org/downloads/"); } catch (Exception) { }
            return 1;
        }
        try
        {
            ProcessStartInfo si = new ProcessStartInfo(py, "\"" + arranque + "\"");
            si.WorkingDirectory = programa;
            si.UseShellExecute = false;
            si.CreateNoWindow = true;
            Process.Start(si);
        }
        catch (Exception e)
        {
            MessageBox.Show("No se pudo abrir el autopiloto:\n" + e.Message, "Autopiloto",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }
}
