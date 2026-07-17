@ECHO OFF
SETLOCAL
SET DIR=%~dp0
SET WRAPPER_JAR=%DIR%gradle\wrapper\gradle-wrapper.jar

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Official Gradle wrapper JAR is missing. Downloading Gradle 9.4.1 wrapper...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%bootstrap-gradle-wrapper.ps1"
  IF ERRORLEVEL 1 EXIT /B 1
)

IF NOT DEFINED JAVA_HOME (
  IF EXIST "C:\Program Files\Android\Android Studio\jbr\bin\java.exe" SET "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
)

IF DEFINED JAVA_HOME (
  "%JAVA_HOME%\bin\java.exe" -classpath "%WRAPPER_JAR%" org.gradle.wrapper.GradleWrapperMain %*
) ELSE (
  java -classpath "%WRAPPER_JAR%" org.gradle.wrapper.GradleWrapperMain %*
)
ENDLOCAL
